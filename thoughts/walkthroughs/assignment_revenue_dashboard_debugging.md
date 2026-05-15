# Assignment Revenue Dashboard Debugging Walkthrough

## What I Investigated

I traced the dashboard from the React property selector through `SecureAPI`, the FastAPI dashboard endpoint, Redis caching, the revenue service, and the seeded Postgres data. The highest-risk path was small: `Dashboard.tsx` -> `RevenueSummary.tsx` -> `/api/v1/dashboard/summary` -> `get_revenue_summary()` -> reservation aggregation.

## Bug 1: Tenant-Unsafe Cache Key

Symptom: Ocean Rentals could see revenue that appeared to belong to another company after refresh.

Root cause: Redis cached revenue as `revenue:{property_id}`. The seed data intentionally uses `prop-001` for both `tenant-a` and `tenant-b`, so one tenant could reuse the other's cached summary.

Fix: The cache key now includes tenant, property, year, and month: `revenue:{tenant_id}:{property_id}:{year}:{month}`. Cached payloads are also checked for matching `tenant_id` before reuse.

Verification: `backend/tests/test_revenue_cache.py` proves `tenant-a/prop-001` and `tenant-b/prop-001` produce different keys.

## Bug 2: All-Tenant Property Selector

Symptom: The frontend allowed any logged-in client to select properties across both tenants.

Root cause: `Dashboard.tsx` used a hardcoded global property list.

Fix: Added `GET /api/v1/dashboard/properties` and updated the dashboard to fetch properties for the authenticated tenant only.

Verification: Direct API calls with each account should show only that tenant's properties. The selector now uses the backend response as the source of truth.

## Bug 3: All-Time Totals Instead Of March Totals

Symptom: Sunset's March totals did not match the March reservation data.

Root cause: The backend summary endpoint accepted only `property_id`, and the service summed all reservations for that property and tenant.

Fix: The endpoint now accepts explicit `month` and `year` query params and the frontend defaults to March 2024.

Verification: Summary calls use `month=3&year=2024`, and tests cover the monthly helper behavior.

## Bug 4: Timezone Month Boundaries

Symptom: A Paris reservation at `2024-02-29 23:30:00+00` should count as March locally, but UTC-only filtering would exclude it.

Root cause: Month boundaries were not calculated in the property's local timezone.

Fix: The service reads the property's timezone, builds local month boundaries, converts them to UTC, then filters `check_in_date` between those UTC instants.

Verification: `test_paris_march_bounds_include_late_february_utc_checkin` confirms March 2024 in `Europe/Paris` starts at `2024-02-29T23:00:00Z`.

## Bug 5: Float And JavaScript Money Precision

Symptom: Finance saw totals off by a few cents.

Root cause: The backend converted `Decimal` totals to `float`, and the frontend rounded JavaScript numbers.

Fix: The backend now keeps `Decimal`, quantizes with `ROUND_HALF_UP`, and returns totals as decimal strings. The frontend formats decimal strings without numeric rounding.

Verification: `test_money_format_returns_decimal_string` covers decimal string formatting and half-up rounding.

## Bug 6: Docker Database Config And Fallback Behavior

Symptom: Revenue requests could fall into fallback data because the database pool built a URL from missing Supabase-specific settings instead of Docker's `DATABASE_URL`.

Root cause: `database_pool.py` ignored `settings.database_url`.

Fix: The pool now uses `settings.database_url`, converts `postgresql://` to `postgresql+asyncpg://`, and reuses the global pool.

Verification: Backend compile and tests should pass. Running the stack should query seeded Postgres instead of falling back because of URL construction.

## Extra Reliability Fixes

Redis read/write failures no longer prevent revenue calculation. The service logs cache failures and computes the response directly.

Fallback data remains available for local assignment resilience, but it is tenant-aware and responses include `is_fallback: true` plus a `fallback_reason` when used.

## Verification Checklist

- Run `python -m compileall app` from `backend`.
- Run `python -m pytest` from `backend`.
- Run `npm run build` from `frontend`.
- Run `npm run lint` from `frontend` if dependencies and scripts are available.
- Start the stack with `docker compose up --build`.
- Log in as `sunset@propertyflow.com` / `client_a_2024` and confirm only Sunset properties appear.
- Log in as `ocean@propertyflow.com` / `client_b_2024` and confirm only Ocean properties appear.
- Query `/api/v1/dashboard/summary?property_id=prop-001&month=3&year=2024` with both tenants and confirm tenant-specific property metadata and decimal-string totals.
- Refresh repeatedly and confirm no cross-tenant revenue or property names appear.

## Presentation Script

Start with the privacy bug: `prop-001` exists for both tenants, but the cache used only property ID. Then show the frontend hardcoded all properties, which made cross-tenant selection possible. Next explain the revenue math: the endpoint lacked month/year, the service summed all time, and timezone boundaries needed to be property-local. Finish with financial precision: backend decimals now cross the API as strings, and the frontend formats strings instead of doing JavaScript rounding.
