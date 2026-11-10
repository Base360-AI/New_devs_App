# Findings: Property Revenue Dashboard

This document lists the bugs behind the three reported problems, how each one was found, the root cause, the fix, and the test that now covers it. The last part lists recommended next steps for the codebase.

Line references marked **before** point to the original code at commit `f8badb754`. You can open them with `git show f8badb754:<path>`. References marked **after** point to the current code.

## Summary

Nine bugs were found and fixed, one commit each. A new backend test suite has 58 tests, all passing.

| Reported problem | Caused by |
|---|---|
| Client A (Sunset Properties): "March totals don't match our records" | Bug 1 (mock data instead of the database), bug 4 (month boundaries in UTC instead of the property's timezone), bug 9 (no way to choose a month in the dashboard) |
| Client B (Ocean Rentals): "sometimes we see revenue that belongs to another company" | Bug 2 (cache key without tenant), bug 3 (unknown users assigned to Sunset's tenant), bug 6 (every tenant's property names shown to everyone) |
| Finance: "totals slightly off by a few cents" | Bug 5 (sub-cent amounts rounded through floats), bug 8 (amounts in different currencies would be added together) |
| Not reported, found during review | Bug 7 (fake "+12%" growth badge shown next to real revenue) |

## Bugs

### 1. The dashboard never read the database and showed hardcoded mock numbers

- **Symptom:** every client saw the same figures, for example prop-001 = 1000.00 from 3 bookings, for both tenants. The real value for Sunset is 2250.00 from 4 bookings.
- **How found:** called `/api/v1/dashboard/summary` as both clients. The backend log showed `Database pool not available` on every request.
- **Root cause (before):**
  - `backend/app/core/database_pool.py:18` built the URL from `settings.supabase_db_*` fields. Those fields do not exist in `config.py`, so initialization failed and the error was swallowed.
  - `database_pool.py:22` used `QueuePool`, which cannot be used with an async engine.
  - `database_pool.py:48` defined `get_session` as `async def`, but callers used it with `async with`, which fails.
  - `backend/app/services/reservations.py:43` created a new pool on every request, and never disposed it.
  - `reservations.py:93` caught every error and returned a hardcoded `mock_data` dictionary keyed only by property ID.
  - `requirements.txt` did not install `greenlet`, which the SQLAlchemy asyncio extension needs.
- **Fix (after):**
  - `database_pool.py:9` builds the URL from `settings.database_url`, using the asyncpg driver.
  - `database_pool.py:23` creates one shared pool, once per process, protected by a lock.
  - `database_pool.py:63` makes `get_session` a plain method that returns a session usable with `async with`.
  - The mock fallback is removed. A database error is logged and the endpoint returns 503.
  - `requirements.txt` now has `sqlalchemy[asyncio]`.
- **Commits:** `a261ade22`, dependency alignment in `pyproject.toml` and `uv.lock` in `991462286`.
- **Tests:** `test_revenue_db_integration.py::test_all_time_total_uses_real_data_not_mock`, `test_dashboard_api.py::test_summary_returns_503_when_data_unavailable`.

### 2. The revenue cache mixed up tenants

- **Symptom:** after Sunset loaded prop-001, Ocean saw Sunset's 2250.00 for its own prop-001 for 5 minutes. Which tenant saw wrong data depended on who loaded first, which explains "sometimes, when we refresh".
- **How found:** after bug 1 was fixed, the same request as Ocean returned Sunset's total. The Redis keys showed only `revenue:prop-001`.
- **Root cause (before):** `backend/app/services/cache.py:13` used the key `revenue:{property_id}`. Property IDs are unique only within a tenant, and `prop-001` exists in both tenants (`database/seed.sql`).
- **Fix (after):** `cache.py:24` uses `revenue:{tenant_id}:{property_id}:{period}`. `cache.py:19` refuses a missing tenant, so a key without a tenant cannot be built.
- **Commit:** `03f3c9a5e`.
- **Tests:** `test_revenue_cache.py`, 6 tests. When the old key was put back temporarily, 3 of them failed.

### 3. Users without a tenant were given Sunset's tenant

- **Symptom:** a valid login for any email other than the two demo clients saw Sunset Properties' revenue.
- **How found:** while testing a "no tenant" case, a token with an unknown email returned HTTP 200 with Sunset's numbers. The auth log showed `tenant=tenant-a`.
- **Root cause (before):**
  - `backend/app/core/tenant_resolver.py:92` ended with `return "tenant-a"` after checking three hardcoded emails. It also ignored the `tenant_id` claim already present in the signed token.
  - `backend/app/api/v1/dashboard.py:14` fell back to a shared `"default_tenant"` value when the tenant was missing.
- **Fix (after):**
  - `tenant_resolver.py:89` reads the tenant claim from the token first.
  - `tenant_resolver.py:106` returns `None` when no tenant is found.
  - `dashboard.py:12-18` (`_require_tenant`) returns 403 when there is no tenant.
- **Commit:** `129f08ee5`.
- **Tests:** `test_tenant_resolver.py`, 9 tests. `test_dashboard_api.py::test_summary_without_tenant_is_forbidden`.

### 4. Month boundaries used UTC instead of the property's timezone

- **Symptom:** Sunset's March total for Beach House Alpha did not match their records.
- **How found:** seed reservation `res-tz-1` checks in at `2024-02-29 23:30 UTC`. For a property in `Europe/Paris` that is `2024-03-01 00:30`, which is March. A UTC month boundary gives March = 1000.000 from 3 bookings. The correct local-time answer is 2250.00 from 4 bookings.
- **Root cause (before):** `backend/app/services/reservations.py:5` (`calculate_monthly_revenue`) built naive UTC dates, had no tenant parameter, and was a stub that always returned `Decimal('0')` (line 32). Nothing called it.
- **Fix (after):**
  - `reservations.py:37` implements the monthly query.
  - `reservations.py:71` compares `check_in_date AT TIME ZONE p.timezone` against the local month start and the next month start, joining `properties` on `(id, tenant_id)`.
  - The summary endpoint accepts optional `month` and `year` (both or neither, otherwise 422).
  - The cache key includes the period.
- **Commit:** `f3c82697c`.
- **Tests:** `test_revenue_db_integration.py::test_booking_late_on_feb_29_utc_counts_as_march_in_paris`, plus the March 2024 table for all six tenant and property pairs.

### 5. Cent rounding went through floats

- **Symptom:** totals could be off by a cent.
- **Root cause (before):**
  - `total_amount` is `NUMERIC(10,3)`, so it holds sub-cent values like `333.333`.
  - The service returned the raw sum. `backend/app/api/v1/dashboard.py:18` converted it with `float()`.
  - The frontend rounded the float with `Math.round(x * 100) / 100` (`RevenueSummary.tsx:64`).
  - Floats cannot represent most decimal amounts exactly, for example `round(2.675, 2)` gives `2.67`.
- **Fix (after):**
  - `reservations.py:11` (`_to_cents`) rounds the exact database sum once, with `Decimal` and `ROUND_HALF_UP`.
  - `dashboard.py:66` also returns `total_revenue_str`, the exact amount as a string. The numeric field stays for the existing frontend.
- **Commit:** `4743cb491`.
- **Tests:** `test_money_rounding.py`, 11 tests, including `2.675` rounding to `2.68`.

### 6. Every tenant saw every tenant's property names

- **Symptom:** Sunset's dropdown listed Ocean's properties, and the other way round. It also labelled Ocean's `prop-001` as "Beach House Alpha", although for Ocean it is "Mountain Lodge Beta".
- **Root cause (before):**
  - `frontend/src/components/Dashboard.tsx:4-10` hardcoded all five properties.
  - `RevenueSummary.tsx:22,31` sent a leftover `X-Simulated-Tenant: candidate` header. The backend ignored it, but it suggested the client could choose its own tenant.
- **Fix (after):**
  - New endpoint `GET /api/v1/dashboard/properties` (`dashboard.py:22`), backed by `list_tenant_properties` (`reservations.py:159`).
  - The dashboard loads the list on start.
  - The simulated-tenant header is removed.
- **Commit:** `1191677f4`.
- **Tests:** `test_dashboard_api.py::test_properties_lists_only_callers_tenant`, `test_revenue_db_integration.py::test_property_list_is_scoped_to_tenant`.

### 7. A fake "+12%" growth badge was shown next to real revenue

- **Root cause (before):** `RevenueSummary.tsx:83-88` rendered a hardcoded green "+12%" badge. The code comment said `Fake trend indicator for premium feel`. Clients preparing board reports saw a growth figure that no data supports.
- **Fix:** removed.
- **Commit:** `801c5eb61`.

### 8. The currency was hardcoded and mixed currencies would be added together

- **Root cause (before):** the `reservations.currency` column exists, and the brief mentions "various amounts and currencies". Both revenue paths still returned `"currency": "USD"`, and `SUM(total_amount)` would add EUR and USD amounts as if they were the same money. All seed data is USD, so this was not visible yet.
- **Fix (after):**
  - `reservations.py:25-35` returns the stored currency. It raises `MixedCurrencyError` when one total would cover more than one currency.
  - `dashboard.py:52` returns 409 in that case.
- **Commit:** `99c90111f`.
- **Tests:** `test_revenue_db_integration.py::test_mixed_currencies_are_not_summed` (adds a temporary EUR booking and removes it), `test_dashboard_api.py::test_summary_returns_409_for_mixed_currencies`.

### 9. The dashboard could not show a single month

- **Symptom:** the backend could compute March (bug 4), but the UI only showed all-time totals, so Sunset could not compare its March figure in the dashboard.
- **Fix:**
  - `Dashboard.tsx` has a month picker labelled "Month (property local time)", with an "All time" reset.
  - `RevenueSummary` sends `month` and `year` and shows the period under the total.
- **Commit:** `cd513f57e`.

## Expected numbers (March 2024, property local time)

| Tenant | Property | Total | Bookings |
|---|---|---|---|
| Sunset (tenant-a) | prop-001 Beach House Alpha | 2,250.00 USD | 4 |
| Sunset (tenant-a) | prop-002 City Apartment Downtown | 4,975.50 USD | 4 |
| Sunset (tenant-a) | prop-003 Country Villa Estate | 6,100.50 USD | 2 |
| Ocean (tenant-b) | prop-001 Mountain Lodge Beta | 0.00 USD | 0 |
| Ocean (tenant-b) | prop-004 Lakeside Cottage | 1,776.50 USD | 4 |
| Ocean (tenant-b) | prop-005 Urban Loft Modern | 3,256.00 USD | 3 |

Before the fixes, Sunset's prop-001 showed 1,000.00 from 3 bookings (mock data). A query with UTC month boundaries gives the same wrong 1,000.000 from 3 bookings.

## How to verify

```bash
docker compose up --build -d
docker compose exec backend pip install -r requirements-dev.txt
docker compose exec backend pytest            # 58 tests
docker compose exec backend pytest -m integration   # 17 tests against the seeded Postgres
```

Then open http://localhost:3000:

1. Log in as Sunset. The dropdown shows only Sunset's three properties.
2. Pick 2024-03: Beach House Alpha shows 2,250.00 USD from 4 bookings. Pick 2024-02: it shows 0.00.
3. Log out and log in as Ocean. Its prop-001 is "Mountain Lodge Beta" with 0.00, and Lakeside Cottage shows 1,776.50 for March.

The dev dependencies are not part of the image. Install them again after any `docker compose up --build`.

## Recommendations

These items are outside the scope of a debugging exercise ("do not rebuild the system"), but they are the changes that would stop this class of bug from coming back. They are ordered by priority.

### Now

**A. Move the backend to a layered architecture.** Today one module mixes concerns: `services/reservations.py` opens database sessions and writes raw SQL, `services/cache.py` creates its own Redis client, and `api/v1/dashboard.py` maps every exception by hand. All three tenant bugs happened in places where one layer had to remember the tenant on its own. A structure like the one in [eslam5464/Fastapi-Template](https://github.com/eslam5464/Fastapi-Template) makes the tenant a required input at every boundary:

```
api/v1/dashboard.py            routes only: parse input, call the service, return a schema
api/deps.py                    get_current_tenant, get_session, get_revenue_service
services/revenue_service.py    business rules: local-time months, cents, currency
repositories/
  reservation_repository.py    all SQL; every method takes tenant_id
  property_repository.py
models/                        SQLAlchemy Property, Reservation
schemas/                       Pydantic RevenueSummaryOut (Decimal money, currency)
core/exceptions.py             TenantRequiredError, MixedCurrencyError, DataUnavailableError
                               mapped to 403 / 409 / 503 in one exception handler
```

Further steps in the same direction:

- Put caching in one wrapper around the service, with one key builder that requires a tenant.
- Replace `database/schema.sql` and the nine `backend/lightning_optimization_*.sql` variants with Alembic migrations.
- Enforce the layer rules with tach or import-linter, for example "api must not import repositories".
- Migrate step by step: move the revenue slice first, which the 58 tests already cover, then the other routers.

**B. Enforce tenant isolation in the database too.**

- Row-level security is enabled on `properties` and `reservations` (`database/schema.sql:35-36`), but no policies exist. Add `USING (tenant_id = current_setting('app.tenant_id'))` and set `app.tenant_id` on each session. Then a query that forgets `WHERE tenant_id` returns nothing instead of another tenant's data.
- Pass the verified JWT payload to `TenantResolver`, instead of reading the claims again with `jwt.get_unverified_claims` (`tenant_resolver.py:89`).
- Remove the email-to-tenant mapping once every token carries the claim.

**C. Security hygiene.**

- Demo passwords are hardcoded in `backend/app/api/v1/login.py:43,73`.
- `secret_key` defaults to `"debug_challenge_secret"` (`config.py:14`). Startup should fail outside development when the default is in use.
- `frontend/.env` is committed.
- The authentication cache is an in-process dictionary (`core/auth.py:20`) kept for 30 minutes. Each worker has its own copy, and a token cannot be revoked. Move it to Redis with a token blacklist, and add rate limiting on login. Both are optional features of the template above.

### Next

**D. Model money and time explicitly.**

- Add a `Money(amount: Decimal, currency: str)` value object, and return per-currency totals or converted totals instead of 409.
- Validate property timezones against the IANA list.
- Agree with finance on the revenue recognition rule. Today revenue counts in the month of check-in. A stay that crosses the end of a month may need to be split by nights.

**E. Cache correctness.**

- Invalidate `revenue:{tenant}:{property}:*` when a reservation is created or changed, or use versioned keys. Today a new booking is invisible for up to 5 minutes.
- Use the shared client in `core/redis_client.py` instead of the second client created in `services/cache.py:7`.

**F. Repository and delivery hygiene.**

- 72,348 `node_modules` files and the `frontend/dist` build output are committed. Remove them and rely on the lockfiles.
- The backend Dockerfile runs `uvicorn --reload`, which is for development only.
- CI runs only pre-commit. Add pytest with a coverage gate, ruff, mypy and a security scan.
- Install dev dependencies in a separate image stage, so a rebuild keeps pytest.
- Remove the obsolete `version:` key from `docker-compose.yml`.

### Later

**G. Code health.**

- `api/v1/city_access_fast.py` and `api/v1/city_access_fixed.py` are two near-duplicate implementations of about 500 lines each.
- `frontend/src/lib/secureApi.ts` is 2,483 lines; split it by domain.
- Replace the remaining `print(` calls in the backend with logging.
- When Supabase is not configured, startup logs `Failed to initialize Supabase connection pool`, and the login page logs `SessionRecovery` errors. Both are noise that hides real errors.

**H. Observability.**

- Add structured logs with `tenant_id` and a request ID.
- Add alerts on the rate of 503 and 409 responses.
- Keep an audit log of which user viewed which tenant's revenue, so a leak can be detected and measured.

## Known leftovers

Items G and H were not changed, because the brief asks to fix the reported issues and not rebuild the system. The Supabase and `SessionRecovery` messages existed before these changes and do not affect the dashboard.
