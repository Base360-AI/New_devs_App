# Findings: Property Revenue Dashboard

Scope: the dashboard has exactly one real code path —
`Dashboard.tsx → RevenueSummary.tsx → GET /api/v1/dashboard/summary → services/cache.py → services/reservations.py → core/database_pool.py`.
Everything else in the repo is unrelated scaffolding and was deliberately left untouched (this is a debugging task, not a rebuild).

## Bugs and fixes

| # | Symptom reported | Root cause | Fix |
|---|---|---|---|
| 1 | **Ocean Rentals** intermittently sees another company's numbers on refresh | `services/cache.py` cached by `revenue:{property_id}` only. Property IDs are unique *per tenant* (PK is `(id, tenant_id)`; both tenants own `prop-001`), so whoever warmed the key served their numbers to the other tenant for the 300 s TTL. | Key is now `revenue:v2:{tenant_id}:{property_id}:{period}`. Cached payload is also checked against the requesting tenant before being served (defense in depth). |
| 2 | Numbers "don't match internal records" (both clients) | The dashboard **never read the database**. `core/database_pool.py` built its DSN from `settings.supabase_db_*` fields that don't exist → `AttributeError`; `get_session` was `async def` but used with `async with`; a new pool was built per request. `calculate_total_revenue` swallowed every exception and returned a **hard-coded mock table** keyed by property only — so `prop-001` showed `1000.00 / 3` to *both* tenants (a second cross-tenant leak, and it hid the outage). | Pool uses `settings.database_url` (rewritten to `postgresql+asyncpg://`), single global pool with lazy, lock-guarded init, `get_session` returns the session. The mock fallback is deleted: DB errors now surface as **503**. Financial data must fail loudly, never fabricate. |
| 3 | **Sunset Properties** March total differs from their books | `calculate_monthly_revenue` used naive `datetime(year, month, 1)` bounds against `TIMESTAMPTZ`, i.e. UTC months. Seed row `res-tz-1` checks in at `2024-02-29 23:30 UTC` = **1 March 00:30 in Europe/Paris**, so 1 250.00 fell into February. The function was also a stub returning `0`, lacked its `tenant_id` param, and was never called. | Month boundaries are evaluated in the property's own timezone: `check_in_date AT TIME ZONE properties.timezone` compared to half-open local bounds. `month`/`year` query params were wired into `/dashboard/summary` and a period picker added to the UI. |
| 4 | Finance sees totals "off by a few cents" | `dashboard.py` did `float(total)` on a `NUMERIC(10,3)` sum, and the UI re-rounded with `Math.round(x*100)/100`. Sub-cent rows (`333.333 + 333.333 + 333.334`) round to `999.99` if rounded per row or through float, vs the correct `1000.00`. | Sum in SQL (exact), round **once** on the total with `Decimal.quantize(0.01, ROUND_HALF_UP)`, serialise as a string. UI formats the string; no float arithmetic anywhere. |
| 5 | Ocean sees Sunset's property names | `Dashboard.tsx` hard-coded all five properties for every tenant. | New tenant-scoped `GET /api/v1/dashboard/properties`; the selector is populated from it. |
| 6 | (security hardening found while investigating) | `dashboard.py` fell back to `"default_tenant"` when the user had no tenant; `TenantResolver` defaulted *unknown* users to `tenant-a`; the UI sent an `X-Simulated-Tenant: candidate` header; the summary endpoint didn't check the property belongs to the caller. | Missing tenant → **403**. Resolver reads the signed JWT claim (`app_metadata.tenant_id`), then a known-account map, else `None`. Header removed. Unknown property for this tenant → **404** (no cross-tenant probing). |

## Expected values after the fix (seed data)

| Login | Property | All time | March 2024 (property tz) |
|---|---|---|---|
| Sunset (tenant-a) | prop-001 Beach House Alpha (Paris) | **2250.00 / 4** | **2250.00 / 4** (UTC logic would say 1000.00 / 3) |
| Sunset | prop-002 / prop-003 | 4975.50 / 4, 6100.50 / 2 | same |
| Ocean (tenant-b) | prop-001 Mountain Lodge Beta (New York) | **0.00 / 0** (was showing Sunset's 1000.00 / 3) | 0.00 / 0 |
| Ocean | prop-004 / prop-005 | 1776.50 / 4, 3256.00 / 3 | same |

## How to verify

```bash
docker compose up --build
# UI: http://localhost:3000  (log in as each client, compare prop-001)
# API: http://localhost:8000/docs

# Unit tests (pure functions, no DB needed)
cd backend && python -m pytest -q

# Cache keys are now tenant-scoped
docker compose exec redis redis-cli KEYS 'revenue:*'
```

## Left as follow-ups (out of scope for a debugging pass)

- `schema.sql` enables RLS on `properties`/`reservations` but defines no policies; the app connects as superuser so RLS is a no-op. Real isolation should add policies keyed on a `current_tenant_id()` setting and connect as a non-superuser role.
- `SECRET_KEY` and DB credentials live in `docker-compose.yml`; move to env/secrets.
- The in-process auth cache keys on a 16-hex token hash for 30 min; fine for now, but token revocation needs the Redis pub/sub path.
- A tenant-aware cache helper that *requires* `tenant_id` (as `revenue_cache_key` now does) should be the only way to touch Redis, so bug #1 cannot be reintroduced.
