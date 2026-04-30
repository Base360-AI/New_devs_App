# Property Revenue Dashboard — Fix Report

This document covers the seven bugs found and fixed during the debugging session, plus the engineering rationale for each. The fixes are listed in a stable order that groups the reported issues first, then the related bugs uncovered while resolving them.

The three reported issues from `ASSIGNMENT.md` (Client A's revenue mismatch, Client B's privacy concern, Finance's "off by a few cents") are all addressed by Fixes #1, #2, and #4 below. The remaining fixes are bugs we found while resolving the reported issues; they're documented because shipping the reported fixes without them would have left the system in a known-broken state.

---

## Fix #1 — Restore the database query path and remove the fabricated-data fallback

### Symptom

`sunset@propertyflow.com`'s dashboard showed `$1,000.00 / 3 reservations` for Beach House Alpha (`prop-001`), but the seed data has four reservations totaling `$2,250.00`. Reservation `res-tz-1` ($1,250.00) was missing from the displayed total. This is exactly the discrepancy Client A reported.

### Root cause

A three-layer cascade in `backend/app/core/database_pool.py`:

1. **Line 18 referenced settings that don't exist on the `Settings` class.** The connection string was being built from `settings.supabase_db_user`, `supabase_db_password`, etc. — none of which are defined in `backend/app/config.py`. Accessing them raised `AttributeError`. The actual setting holding the URL is `settings.database_url`, populated by docker-compose.
2. **`poolclass=QueuePool` is incompatible with `create_async_engine`.** Once the URL was fixed, the next layer surfaced: `Pool class QueuePool cannot be used with asyncio engine`. Async engines need a different default pool.
3. **`async def get_session()` returned a coroutine, not an async context manager.** With the engine initialized, callers doing `async with db_pool.get_session() as session:` got `'coroutine' object does not support the asynchronous context manager protocol`.

The exception bubbled into `services/reservations.py::calculate_total_revenue`, which had a broad `except Exception` returning a hard-coded `mock_data` dict keyed only on `property_id`. That dict had two effects: it **silently fabricated revenue numbers**, and it **ignored `tenant_id`** — making it both the source of Client A's reported mismatch and a latent cross-tenant leak.

### Files changed

- `backend/app/core/database_pool.py`
- `backend/app/services/reservations.py`

### What changed

In `database_pool.py`: removed the `QueuePool` import, switched to `settings.database_url` (with `+asyncpg` driver suffix), dropped the `poolclass` kwarg, and changed `get_session` from `async def` to plain `def` so it returns an async-context-manager directly.

In `reservations.py`: removed the `mock_data` dict, removed the broad `except Exception`, and rewrote `calculate_total_revenue` to do the SQL aggregation cleanly. If the database is unreachable, the exception now propagates to the API layer, which returns 5xx — the system fails closed rather than fabricating revenue.

### What it achieves

- The SQL aggregation actually runs. `prop-001 / tenant-a` now correctly reports `$2,250.00 / 4` (matching `database/seed.sql`).
- A real DB outage produces a 5xx error and a "Failed to load revenue data" message in the UI, not silently fabricated numbers.
- The tenant-blind `mock_data` dict — itself a privacy hole — is gone.

### Notable observation

The original `mock_data` dict was calibrated to match the real seed totals for **four of five properties** (prop-002 through prop-005). Only `prop-001 / tenant-a` differed — by exactly $1,250, the value of the timezone-test reservation `res-tz-1`. That's why the bug is solvable: `prop-001` is the breadcrumb that tells you the system isn't reading from the database at all.

---

## Fix #2 — Scope the revenue cache key by tenant

### Symptom

After Fix #1, this bug became reproducible: log in as tenant-a, view `prop-001` (returns the real $2,250.00). Within five minutes, log in as tenant-b and view their `prop-001` (Mountain Lodge Beta, no reservations seeded). Tenant-b's dashboard showed $2,250.00 / 4 reservations — not their own data, but tenant-a's. This is the privacy violation Client B reported.

### Root cause

`backend/app/services/cache.py:13`:

```python
cache_key = f"revenue:{property_id}"
```

The Redis key contains only `property_id`. Both tenants own a `prop-001` (the schema's composite PK `(id, tenant_id)` allows it), so whichever tenant queried first wrote *their* numbers to `revenue:prop-001`, and the next tenant got the cached value back for the full 5-minute TTL.

This bug was masked by Fix #1's bug: the `mock_data` fallback returned identical fabricated numbers for both tenants regardless of `tenant_id`, so until SQL was alive, "matching numbers" looked normal.

### Files changed

- `backend/app/services/cache.py`

### What changed

```diff
-    cache_key = f"revenue:{property_id}"
+    cache_key = f"revenue:{tenant_id}:{property_id}"
```

### What it achieves

- Cache entries are properly tenant-partitioned: `revenue:tenant-a:prop-001` and `revenue:tenant-b:prop-001` are independent keys.
- Tenant-b's `prop-001` correctly reads as `$0.00 / 0 reservations` instead of inheriting tenant-a's numbers.
- No cross-tenant data leak via the cache layer.

### Notable observation

The composite primary key `PRIMARY KEY (id, tenant_id)` in `database/schema.sql` was the schema-level signal that `property_id` alone isn't unique. Any cache, lookup map, or memoization in this codebase that keys on `property_id` alone is a privacy time bomb. Worth a short audit pass before further work in this area.

---

## Fix #3 — Replace the hardcoded property dropdown with a tenant-scoped fetch

### Symptom

Both tenants saw the same five properties in the dropdown, all labeled with **tenant-a's names**. `ocean@propertyflow.com` (tenant-b) saw "Beach House Alpha" in the dropdown — but tenant-b's `prop-001` is actually "Mountain Lodge Beta" in New York. Each tenant also saw two ghost properties that don't belong to them (returning $0 / 0 reservations).

This was a major part of Client B's complaint — *"we see revenue numbers that look like they belong to another company"* — even when the underlying SQL was tenant-correct, the *labels* told them otherwise.

### Root cause

`frontend/src/components/Dashboard.tsx` had a static array compiled into the bundle:

```tsx
const PROPERTIES = [
  { id: 'prop-001', name: 'Beach House Alpha' },
  ...
];
```

The same five entries rendered for every user, with names matching tenant-a's seeded data. There was no API call to fetch *this tenant's* properties.

### Files changed

- `backend/app/api/v1/dashboard.py` *(added `/dashboard/properties` endpoint)*
- `frontend/src/lib/secureApi.ts` *(added `getProperties` method)*
- `frontend/src/components/Dashboard.tsx` *(replaced hardcoded array with fetch)*

### What changed

A new `GET /api/v1/dashboard/properties` endpoint reads `tenant_id` from the authenticated user, queries the `properties` table filtered by tenant, and returns `{id, name, timezone}`. The Dashboard component now fetches on mount and renders the result.

### What it achieves

- Tenant-a sees Beach House Alpha, City Apartment Downtown, Country Villa Estate (Paris properties).
- Tenant-b sees Mountain Lodge Beta, Lakeside Cottage, Urban Loft Modern (New York properties).
- The "ghost" $0 entries (properties the tenant doesn't own) are gone.
- Property metadata (notably `timezone`) is now available on the frontend, useful for upcoming features.

---

## Fix #4 — Round revenue in Decimal space before the float cast

### Symptom

Finance reported revenue totals "slightly off by a few cents here and there" without being able to pin down when. The seed data alone happens not to trigger drift (all totals sum cleanly), but the bug is sitting there for any reservation amount whose binary float representation drifts across a half-cent boundary.

### Root cause

`backend/app/api/v1/dashboard.py`:

```python
total_revenue_float = float(revenue_data['total'])
```

The value arriving as `revenue_data['total']` is a stringified `Decimal` (e.g. `"2250.000"`) — full sub-cent precision intact through the SQL aggregation, the JSON cache, and the dict pass-through. This line drops it into a binary float, which can't represent most decimal fractions exactly. The frontend's `Math.round(value * 100) / 100` then operates on the lossy float, and certain values land on the wrong cent.

Canonical case: a reservation total of `$1.005`.

```
Decimal('1.005')               → exact
float(Decimal('1.005'))        → 1.0049999999999999  (closest representable double)
1.0049999... * 100             → 100.49999999999999
Math.round(100.4999...)        → 100   (rounds DOWN, below 100.5)
100 / 100                      → $1.00 ← wrong; correct is $1.01
```

The frontend can't recover precision that was thrown away on the backend, so the fix has to happen *before* the float cast.

### Files changed

- `backend/app/api/v1/dashboard.py`

### What changed

Both `/dashboard/summary` and `/dashboard/monthly` now round in `Decimal` space before crossing into float:

```python
def _round_to_cents(value: str) -> float:
    return float(Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
```

`ROUND_HALF_UP` is the rounding mode most humans expect (`0.005` → `0.01`). The resulting float is always a clean 2-decimal value, so the frontend's display rounding is a no-op confirming what's already correct.

### What it achieves

- A reservation of `$1.005` correctly displays as `$1.01` (verified end-to-end with a test insertion).
- All existing seed-data totals remain unchanged (regression check passed for all six tenant/property combinations).
- Rounding policy is centralized on the backend — all clients (dashboard, future CSV export, mobile app) agree automatically.

### Worth confirming with Finance

We chose `ROUND_HALF_UP`. Some accounting standards mandate `ROUND_HALF_EVEN` ("banker's rounding"). The two differ on values exactly at the half-cent. Worth a one-line confirmation before this ships to production.

---

## Fix #5 — Implement timezone-aware monthly revenue

### Symptom

`services/reservations.py::calculate_monthly_revenue` was a stub that built a SQL query but returned `Decimal('0')` without executing it. Even if the function had been wired to an endpoint (it wasn't), the date boundaries were naive datetimes (`datetime(year, month, 1)`) — which compared against `TIMESTAMP WITH TIME ZONE` columns produces results that depend on the database session timezone. Combined with properties spanning Paris and New York, this is exactly the kind of bug that produces "off by a day" or "off by a month" complaints.

The seed data deliberately includes one reservation that exposes this: `res-tz-1`, with `check_in_date = '2024-02-29 23:30:00+00'` UTC — which is `00:30` on March 1 in Paris time. Whether this booking belongs to "February" or "March" depends on whose timezone you ask.

### Root cause

The original function:

```python
async def calculate_monthly_revenue(property_id: str, month: int, year: int):
    start_date = datetime(year, month, 1)            # ← naive, no tzinfo
    end_date = datetime(year, month + 1, 1)          # ← naive, no tzinfo
    print(f"DEBUG: Querying revenue for {property_id} from {start_date} to {end_date}")
    # ... SQL string that's never executed ...
    return Decimal('0')                              # ← stub
```

Three issues: stub return value, naive datetimes, and a `print()` that should be a logger call.

### Files changed

- `backend/app/services/reservations.py`
- `backend/app/api/v1/dashboard.py` *(new `/dashboard/monthly` endpoint)*
- `frontend/src/lib/secureApi.ts` *(new `getMonthlyRevenue` method)*
- `frontend/src/components/RevenueSummary.tsx` *(new "March 2024 revenue" line)*

### What changed

`calculate_monthly_revenue` now:

- Accepts `tenant_id` (a previously absent argument).
- Builds boundaries as `datetime(year, month, 1, tzinfo=timezone.utc)` — explicitly UTC-anchored.
- Actually executes the SQL via the database pool.
- Uses the same `Decimal`-precise return shape as `calculate_total_revenue`.

A new `GET /api/v1/dashboard/monthly?property_id=…&month=…&year=…` endpoint surfaces it, defaulting to March 2024 (the only month the seed data covers). The frontend displays the monthly figure under the all-time total. The dashboard's existing copy ("Monthly performance insights") finally reflects what's shown.

### What it achieves

- Monthly aggregation is deterministic across environments — UTC midnight boundaries produce the same answer regardless of database session timezone or daylight-saving.
- `res-tz-1` (Feb 29 23:30 UTC, $1,250) is correctly excluded from UTC March, included in UTC February. This is the explicit, defensible answer.

### Open design question

UTC-anchored boundaries are deterministic but may not be what every tenant expects. From Sunset Properties' (Paris) perspective, `res-tz-1` is a March booking — it falls at 00:30 Paris time on March 1. A future enhancement would compute month boundaries in each *property's local timezone* (the `properties.timezone` column already stores it). That's a deliberate next step, not a finished one — the current implementation makes the boundary policy explicit and auditable rather than environment-dependent.

---

## Fix #6 — Resolve tenant from JWT claims, not a hardcoded email map

### Symptom

`backend/app/core/tenant_resolver.py:84-92`:

```python
if user_email == "sunset@propertyflow.com":   return "tenant-a"
if user_email == "ocean@propertyflow.com":    return "tenant-b"
if user_email == "candidate@propertyflow.com": return "tenant-a"
return "tenant-a"   # ← any unknown user inherits tenant-a
```

A hard-coded email-to-tenant map with a default return of `"tenant-a"` for any unrecognized email. Today our two demo users hit the explicit branches, but if anyone ever introduces a third user (or a malicious user obtains a valid token), they silently gain tenant-a's data.

### Root cause

The same file already contained a static method `resolve_tenant_from_token` that *correctly* extracts tenant_id from JWT claims (`app_metadata.tenant_id`, `user_metadata.tenant_id`, top-level `tenant_id`). It just wasn't being called by `resolve_tenant_id`. Looks like a half-finished refactor — the JWT-based extractor was written but never wired up.

### Files changed

- `backend/app/core/tenant_resolver.py`

### What changed

`resolve_tenant_id` now decodes the JWT (signature verification was already done upstream), extracts the tenant_id via `resolve_tenant_from_token`, and returns `None` if no tenant_id can be derived — leaving the decision to refuse the request to the API layer (which Fix #7 then enforces).

### What it achieves

- New users can be added without touching this file — their `tenant_id` is derived from the JWT claim.
- A user without a tenant_id in their token is refused, not silently granted tenant-a access.
- The latent privacy hole that would have triggered the moment a third user was added is closed.

### Verification

A token without `tenant_id` in metadata results in `resolve_tenant_id` returning `None`, which propagates to the dashboard endpoints, which refuse with HTTP 400 (see Fix #7).

---

## Fix #7 — Refuse dashboard requests without tenant context

### Symptom

`backend/app/api/v1/dashboard.py:40`:

```python
tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"
```

If the authenticated user lacked a `tenant_id` for any reason, the endpoint queried the database with `tenant_id = "default_tenant"`. Today this returns `$0 / 0 reservations` (no rows match), so it's not actively leaking — but the moment anyone seeds data with `tenant_id='default_tenant'` (test fixture, migration, anything), every unauthenticated-but-tenant-less request gets it.

### Root cause

A silent fallback on a security-critical value. The pattern of `getattr(..., default) or default` masks a missing tenant context as a successful but empty query, instead of refusing the request.

### Files changed

- `backend/app/api/v1/dashboard.py`

### What changed

Replaced the silent fallback with a helper that raises:

```python
def _require_tenant(current_user) -> str:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context for user")
    return tenant_id
```

All three dashboard endpoints (`/properties`, `/summary`, `/monthly`) now use this helper.

### What it achieves

- A request without tenant context is refused with HTTP 400 instead of silently running with a "default_tenant" identity.
- The contract is now consistent across the three dashboard endpoints (the new `/properties` endpoint already had this behavior; `/summary` was the outlier).
- Combined with Fix #6, a user whose JWT lacks a `tenant_id` claim is reliably refused at the API layer rather than silently inheriting tenant-a's data.

### Verification

Forging a JWT signed with the dev secret but missing `app_metadata.tenant_id` and hitting `/dashboard/summary` returns:

```
HTTP 400  {"detail":"No tenant context for user"}
```

---

## Summary of files changed

| File | Fixes touched |
|---|---|
| `backend/app/core/database_pool.py` | #1 |
| `backend/app/services/reservations.py` | #1, #5 |
| `backend/app/services/cache.py` | #2 |
| `backend/app/api/v1/dashboard.py` | #3, #4, #5, #7 |
| `backend/app/core/tenant_resolver.py` | #6 |
| `frontend/src/lib/secureApi.ts` | #3, #5 |
| `frontend/src/components/Dashboard.tsx` | #3 |
| `frontend/src/components/RevenueSummary.tsx` | #5 |

## How to verify

```bash
docker compose up --build
docker compose exec redis redis-cli FLUSHDB

# Login both tenants
TOKEN_A=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"sunset@propertyflow.com","password":"client_a_2024"}' | jq -r .access_token)
TOKEN_B=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"ocean@propertyflow.com","password":"client_b_2024"}' | jq -r .access_token)

# Each tenant sees only their own properties with correct names
curl -s -H "Authorization: Bearer $TOKEN_A" http://localhost:8000/api/v1/dashboard/properties | jq
curl -s -H "Authorization: Bearer $TOKEN_B" http://localhost:8000/api/v1/dashboard/properties | jq

# Total revenue per property — should match seed.sql sums exactly
curl -s -H "Authorization: Bearer $TOKEN_A" \
  "http://localhost:8000/api/v1/dashboard/summary?property_id=prop-001" | jq

# Monthly revenue (UTC March 2024) — explicit boundary, deterministic
curl -s -H "Authorization: Bearer $TOKEN_A" \
  "http://localhost:8000/api/v1/dashboard/monthly?property_id=prop-001&month=3&year=2024" | jq
```

Ground-truth comparison from Postgres:

```bash
docker compose exec db psql -U postgres -d propertyflow \
  -c "SELECT property_id, tenant_id, SUM(total_amount), COUNT(*) FROM reservations GROUP BY 1,2 ORDER BY 1,2;"
```

## Expected post-fix dashboard values

| Tenant | Property | All-time revenue | Reservations |
|---|---|---|---|
| tenant-a / Sunset | Beach House Alpha (`prop-001`) | $2,250.00 | 4 |
| tenant-a / Sunset | City Apartment Downtown (`prop-002`) | $4,975.50 | 4 |
| tenant-a / Sunset | Country Villa Estate (`prop-003`) | $6,100.50 | 2 |
| tenant-b / Ocean | Mountain Lodge Beta (`prop-001`) | $0.00 | 0 |
| tenant-b / Ocean | Lakeside Cottage (`prop-004`) | $1,776.50 | 4 |
| tenant-b / Ocean | Urban Loft Modern (`prop-005`) | $3,256.00 | 3 |

UTC-March 2024 monthly revenue:

| Tenant | Property | March revenue | March reservations |
|---|---|---|---|
| tenant-a | Beach House Alpha | $1,000.00 | 3 |
| tenant-a | City Apartment Downtown | $4,975.50 | 4 |
| tenant-a | Country Villa Estate | $6,100.50 | 2 |
| tenant-b | Mountain Lodge Beta | $0.00 | 0 |
| tenant-b | Lakeside Cottage | $1,776.50 | 4 |
| tenant-b | Urban Loft Modern | $3,256.00 | 3 |

(Beach House Alpha shows `$1,000 / 3` for March because `res-tz-1` falls in UTC February, even though it's a March booking from Paris's perspective — this is the open design question called out in Fix #5.)

## Out-of-scope observations

Things noticed during the audit but deliberately not changed:

- **`debugTenant` prop and `X-Simulated-Tenant` header** in `RevenueSummary.tsx` and `secureApi.ts`. The frontend always sends `X-Simulated-Tenant: candidate`, but the backend doesn't read the header — so today this is dead code. It's a footgun: the moment someone wires up "tenant simulation" on the backend for a debug flow, the prop becomes a tenant-bypass vulnerability. Recommend deleting in a follow-up cleanup PR.
- **`calculate_total_revenue` instantiates a new `DatabasePool` per request.** The module already declares a singleton (`db_pool`), but the function ignores it and creates a fresh one each call. Costs nothing in correctness but leaks engine objects under load. A small refactor.
- **Two hard-coded `ADMIN_EMAILS` lists** with slightly different contents in `core/auth.py` and `api/v1/login.py`. Neither demo tenant is in either, so the live flow doesn't depend on them, but they should converge.
- **Lots of dead infrastructure code** (`core/persistent_sessions.py`, `core/token_*.py`, `core/circuit_breaker_fallback.py`, etc.) wired up in `main.py` but unused by the live flow. Intentionally not touched — out of scope for the assignment.
