---
date: 2026-05-15T15:52:40+03:00
git_commit: d1835ec5d24a8be7987cae992a17296f17e5c150
branch: main
repository: New_devs_App
topic: "Assignment revenue dashboard bug investigation"
tags: [research, codebase, assignment, dashboard, revenue, tenancy, cache, timezone, finance]
last_updated: 2026-05-15
last_updated_by: OpenCode
last_updated_note: "Added follow-up research for implementation decisions from open questions"
---

## Ticket Synopsis
The ticket requests a broad bug investigation for the Property Revenue Dashboard assignment. Known risks are incorrect March revenue totals for Sunset Properties, possible cross-tenant revenue exposure for Ocean Rentals after refresh, and small financial discrepancies of a few cents. Scope includes backend, frontend, API endpoints, cache behavior, tenant isolation, timezone/month boundaries, seed data, Docker/config issues if needed, and small targeted tests when useful. Mocked challenge data may be intentional, so this research distinguishes assignment fixtures from bugs that break correctness, privacy, or verification.

## Summary
The main assignment surface is small: `/api/v1/dashboard/summary` calls a Redis-backed revenue summary service, and the React dashboard calls that endpoint for a selected property. The highest-risk bugs cluster around tenant scoping, cache keys, financial precision, and incomplete monthly/timezone handling.

The strongest likely bug is backend cache contamination. `get_revenue_summary()` receives `tenant_id` but uses `revenue:{property_id}` as its Redis key, so two tenants that share a property ID can reuse each other's cached revenue response. The seed data intentionally gives both tenants `prop-001`, which makes this a direct explanation for Ocean Rentals seeing another company's numbers after refresh.

The second likely bug is property selection leakage in the frontend. `Dashboard.tsx` renders all five properties for every logged-in user, including properties owned by the other tenant. The backend query filters by tenant, so unauthorized selections may return zero or fallback/mock values, but the UI still exposes other tenants' property names and allows confusing cross-tenant requests.

The third likely bug is financial precision loss. The backend converts revenue totals from string/Decimal-like values to `float`, and the frontend performs `Math.round(data.total_revenue * 100) / 100`. The seed data includes three sub-cent values, `333.333`, `333.333`, and `333.334`, clearly designed to expose cents-level rounding behavior. The API should preserve money as decimal-safe values or formatted strings until final display.

The fourth likely bug is that monthly revenue and timezone handling are not implemented in the live endpoint. `calculate_monthly_revenue()` contains month boundary logic but returns `Decimal('0')`, and `/dashboard/summary` has no month/year parameters. The live `calculate_total_revenue()` sums all reservations for a property and tenant. Since the assignment specifically mentions March and properties in Paris/New York, the endpoint probably needs month-aware and property-timezone-aware aggregation.

The mocked/fallback data is not automatically a bug because the assignment may use fixtures. It becomes a bug if it masks database connection failures or returns tenant-insensitive totals. The fallback currently returns property-specific data without considering `tenant_id`, and one duplicated property ID, `prop-001`, receives the same fallback for both tenants.

Subagent note: the requested Task subagents failed with `ProviderModelNotFoundError` in this environment. I followed the same Locate, Pattern, and Analyze phases manually with read-only searches and file reads.

## Detailed Findings

### Backend Dashboard Endpoint
- `backend/app/api/v1/dashboard.py:8-16` defines `GET /dashboard/summary`, requires `property_id`, authenticates the request, resolves `tenant_id`, and calls `get_revenue_summary(property_id, tenant_id)`.
- `backend/app/api/v1/dashboard.py:14` uses `getattr(current_user, "tenant_id", "default_tenant")`, which is appropriate for the `AuthenticatedUser` model but would silently fall back to `default_tenant` if auth ever returned an unexpected dict/object. Because this is a protected route, a hard failure would be safer than silently using a default tenant.
- `backend/app/api/v1/dashboard.py:18-24` converts `revenue_data['total']` to `float` before returning `total_revenue`. This is risky for money and directly relates to the cents-level finance report.
- `backend/app/main.py:184-185` includes the dashboard router under `/api/v1`, so the full endpoint is `/api/v1/dashboard/summary`.

### Backend Cache And Tenant Isolation
- `backend/app/services/cache.py:9-13` accepts both `property_id` and `tenant_id`, but builds `cache_key = f"revenue:{property_id}"`.
- `backend/app/services/cache.py:16-18` returns cached JSON directly without validating that the cached payload's `tenant_id` matches the current authenticated tenant.
- `backend/app/services/cache.py:24-27` computes tenant-scoped data, then stores it under the tenant-insensitive key for five minutes.
- `database/seed.sql:8-9` intentionally gives both tenants the same property ID, `prop-001`, with different names and time zones. That makes `revenue:prop-001` a cross-tenant collision key.
- This is the clearest explanation for the assignment's privacy symptom: whichever tenant first populates `revenue:prop-001` can determine what the other tenant sees for the duplicated property ID until the cache expires or is cleared.

### Backend Revenue Aggregation
- `backend/app/services/reservations.py:34-59` implements `calculate_total_revenue(property_id, tenant_id)` with SQL that filters by both `property_id` and `tenant_id`, which is the right tenant isolation pattern for the database query.
- `backend/app/services/reservations.py:51-59` sums all reservations for the property and tenant with no month or year filter. This conflicts with the assignment's March-specific report.
- `backend/app/services/reservations.py:68-74` wraps the SQL aggregate in `Decimal(str(row.total_revenue))` and returns `str(total_revenue)`. This is safer than returning a float from the service, but precision is lost later in the API response.
- `backend/app/services/reservations.py:91-109` returns fallback mock totals when the database path fails. This may be intentional for the challenge environment, but the fallback ignores `tenant_id` and can return the same `prop-001` value for both tenants.
- `backend/app/core/database_pool.py:18-21` builds a database URL from Supabase-specific settings, not from `settings.database_url`. `docker-compose.yml:8-11` provides `DATABASE_URL`, but not `SUPABASE_DB_USER`, `SUPABASE_DB_PASSWORD`, `SUPABASE_DB_HOST`, `SUPABASE_DB_PORT`, or `SUPABASE_DB_NAME`. This likely makes the database pool fail and triggers the fallback mock path.
- `backend/app/config.py:12` defines `database_url` with the correct Docker default, so the minimal fix may be to have the pool use `settings.database_url` converted to the async driver.

### Monthly And Timezone Handling
- `backend/app/services/reservations.py:5-32` defines `calculate_monthly_revenue(property_id, month, year, db_session=None)`, but it has no `tenant_id` parameter and returns `Decimal('0')` unconditionally.
- `backend/app/services/reservations.py:10-15` builds naive Python datetimes for month boundaries. It does not account for each property's local timezone.
- `database/schema.sql:16` stores a timezone on each property, and `database/seed.sql:8-13` uses `Europe/Paris` and `America/New_York`.
- `database/seed.sql:19` includes a booking at `2024-02-29 23:30:00+00` for a Paris property. In Europe/Paris, that is March 1 locally, which is likely a deliberate month-boundary test case.
- `backend/app/api/v1/dashboard.py:8-16` does not accept `month` or `year`, so the dashboard cannot request March-specific totals even though the assignment asks for March investigation.

### Financial Precision And Rounding
- `database/schema.sql:28` stores `total_amount NUMERIC(10, 3)`, explicitly allowing sub-cent precision.
- `database/seed.sql:24-26` includes `333.333`, `333.333`, and `333.334`, which sum exactly to `1000.000`. This looks intentional for precision testing.
- `backend/app/api/v1/dashboard.py:18-22` converts the service's string total to `float`, which can introduce binary floating-point representation issues and strips the API of decimal semantics.
- `frontend/src/components/RevenueSummary.tsx:64` rounds `data.total_revenue` with JavaScript number arithmetic. This may hide backend precision mismatches and should not be the source of financial truth.
- `frontend/src/components/RevenueSummary.tsx:105-114` has a precision warning path, but it only shows when `showRaw` is true, and normal users never pass `showRaw` from `Dashboard.tsx`.

### Frontend Dashboard Data Flow
- `frontend/src/components/Dashboard.tsx:4-10` hardcodes all five properties globally, including properties for both tenants.
- `frontend/src/components/Dashboard.tsx:13` defaults to `prop-001`, which is deliberately duplicated across tenants in seed data.
- `frontend/src/components/Dashboard.tsx:38-42` renders all hardcoded properties in the selector. Tenant A can see Tenant B property names, and Tenant B can see Tenant A property names.
- `frontend/src/components/Dashboard.tsx:49` passes only the selected property ID to `RevenueSummary`, with no month/year and no tenant-aware property metadata.
- `frontend/src/components/RevenueSummary.tsx:22-33` sets `activeTenant` to `debugTenant || 'candidate'` and passes it as `X-Simulated-Tenant`. The backend dashboard endpoint ignores this header and uses JWT auth, so this option is either dead debug code or misleading. It does not fix tenant selection.
- `frontend/src/lib/secureApi.ts:1455-1468` appends a timestamp `_t` to the dashboard request and sends `X-Simulated-Tenant` when provided. The timestamp bypasses frontend request cache for every dashboard call, but it does not affect backend Redis cache.

### Frontend Authentication And Session State
- `frontend/src/lib/supabase.ts:1-6` aliases `supabase` to the local auth client for this challenge.
- `frontend/src/lib/localAuthClient.ts:79-105` logs in through `/api/v1/auth/login` and persists the returned session in `localStorage` under `base360-auth-token`.
- `frontend/src/lib/localAuthClient.ts:122-139` removes that stored session on sign out.
- `frontend/src/contexts/AuthContext.new.tsx:275-290` clears `localStorage` and `sessionStorage` during logout, then calls local auth sign-out. This is heavy-handed but helps avoid cross-client local state when manually switching accounts.
- `frontend/src/lib/secureApi.ts:148-165` clears frontend request caches when the cached token changes. That is a good pattern, but it cannot prevent backend Redis cache collisions.
- `frontend/src/lib/secureApi.ts:187-198` extracts `payload.user_metadata?.tenant_id || payload.tenant_id` and rejects tenant IDs unless they match a UUID regex. Challenge tenant IDs are `tenant-a` and `tenant-b`, so frontend tenant-aware request caching is bypassed for these users. This is not necessarily a correctness bug because bypassing cache is safer, but it means frontend cache isolation is not being exercised in this assignment.

### Backend Authentication
- `backend/app/api/v1/login.py:42-100` has static challenge credentials for Sunset Properties and Ocean Rentals and embeds `tenant-a`/`tenant-b` in JWT `app_metadata`.
- `backend/app/core/auth.py:106-128` decodes custom JWT tokens and wraps them in a mock user object with `app_metadata`.
- `backend/app/core/auth.py:251-257` resolves tenant ID through `TenantResolver`, so the dashboard endpoint should receive a tenant-scoped authenticated user.
- `backend/app/core/auth.py:280-284` caches auth results by token hash. This cache is token-specific and is less suspicious than the revenue Redis cache.

### Database And Seed Data
- `database/schema.sql:12-19` defines `properties` with composite primary key `(id, tenant_id)`, which permits the same property ID across tenants by design.
- `database/schema.sql:22-31` defines `reservations` with `property_id`, `tenant_id`, timezone-aware dates, and numeric amounts.
- `database/schema.sql:34-36` enables row-level security but defines no policies. In Postgres, enabled RLS with no policies denies access for non-owner roles, but this app likely connects as the database owner. Application-level tenant filters remain the active protection.
- `database/seed.sql:8-13` sets tenant-specific properties and time zones.
- `database/seed.sql:19` creates the Paris boundary reservation that likely belongs in March locally.
- `database/seed.sql:24-47` creates March reservations for both tenants.

### Tests And Verification Surface
- No backend tests were found under `backend/tests/**/*`.
- No frontend test files matching `frontend/src/**/*.test.*` were found.
- `backend/pyproject.toml:42-44` configures pytest paths and Python path, so adding backend tests is supported by configuration.
- `frontend/package.json:6-12` defines `dev`, `build`, `watch`, `lint`, and `preview`, but no test script.
- `backend/requirements.txt:1-29` includes `httpx`, FastAPI, SQLAlchemy, Redis, and asyncpg, so targeted API/service tests are feasible.

## Code References
- `backend/app/api/v1/dashboard.py:8-24` - Dashboard summary endpoint, tenant extraction, float conversion, response shape.
- `backend/app/services/cache.py:9-29` - Redis revenue cache, currently keyed only by property ID.
- `backend/app/services/reservations.py:5-32` - Placeholder monthly revenue function with no tenant ID and no real DB execution.
- `backend/app/services/reservations.py:34-109` - Total revenue query and fallback mock data.
- `backend/app/core/database_pool.py:18-21` - Database URL built from missing Supabase-specific settings instead of Docker `DATABASE_URL`.
- `backend/app/config.py:12-14` - Docker-compatible `database_url`, `redis_url`, and `secret_key` defaults.
- `backend/app/api/v1/login.py:42-100` - Static challenge login credentials and tenant JWT metadata.
- `backend/app/core/auth.py:106-128` - Custom JWT decoding path for challenge tokens.
- `frontend/src/components/Dashboard.tsx:4-13` - Global hardcoded properties and default `prop-001` selection.
- `frontend/src/components/Dashboard.tsx:38-49` - Property selector and `RevenueSummary` wiring.
- `frontend/src/components/RevenueSummary.tsx:22-44` - Revenue fetch effect and unused/misleading simulated tenant option.
- `frontend/src/components/RevenueSummary.tsx:64-82` - JavaScript rounding and formatted display.
- `frontend/src/lib/secureApi.ts:1455-1468` - Dashboard API call with timestamp and simulated tenant header.
- `frontend/src/lib/secureApi.ts:148-165` - Frontend cache clearing when access token changes.
- `frontend/src/lib/secureApi.ts:187-198` - Tenant ID UUID validation that rejects `tenant-a`/`tenant-b`.
- `frontend/src/lib/localAuthClient.ts:79-105` - Local login and persisted session creation.
- `database/schema.sql:12-31` - Composite property key, reservation schema, timezone-aware dates, numeric amount precision.
- `database/seed.sql:8-19` - Duplicated `prop-001` across tenants and Paris timezone boundary reservation.
- `database/seed.sql:24-47` - March reservation fixture data for both tenants.
- `docker-compose.yml:8-11` - Backend receives `DATABASE_URL`, `REDIS_URL`, and `SECRET_KEY`.

## Architecture Insights
The assignment appears to be a stripped challenge layer grafted onto a larger property management app. The live assignment path is narrow: local auth, dashboard endpoint, Redis cache, revenue service, and the hardcoded React dashboard. Many broader app files exist, but most are not involved in the reported behavior.

The database schema is intentionally multi-tenant by composite property keys. Because property IDs can repeat across tenants, every query and every cache key must include `tenant_id`. The SQL query does this; the Redis key does not.

The seed data appears intentionally crafted to expose three bug classes: duplicated property IDs for cache/tenant leaks, sub-cent amounts for financial precision, and UTC timestamps near a local month boundary for timezone correctness.

Mock/fallback data should be treated carefully. It may be an intentional challenge convenience, but it should not obscure the real Docker database. If fallback remains, it must be tenant-aware and clearly marked in responses/logs so it does not look like authoritative data.

The frontend currently treats property selection as global static configuration. A safer architecture would fetch tenant-scoped properties from the backend or derive them from an authenticated, tenant-scoped endpoint. For a minimal assignment fix, a tenant-aware static mapping may be acceptable if adding a property endpoint is out of scope.

## Historical Context (from thoughts/)
No prior architecture, plans, or research documents were found under `thoughts/`. The only existing document before this research was `thoughts/tickets/bug_assignment_debugging.md`.

## Related Research
No related research documents existed at the time of this investigation.

## Open Questions
- Resolved: preserve fallback mock data for demo resilience, but make it tenant-aware and clearly log or flag fallback behavior.
- Resolved: add explicit `month` and `year` query parameters, and default the dashboard UI to March 2024 for the assignment.
- Resolved: return money as decimal strings, such as `"1250.00"`, and avoid float conversion for financial values.
- Resolved: add a small backend endpoint for tenant-scoped properties and have the dashboard fetch it.
- Resolved: show a small UI label such as `March 2024, property local time` to make timezone behavior clear in the demo.

## Follow-up Research 2026-05-15T15:52:40+03:00
The user accepted the recommended answers for all open implementation questions.

### Decisions
- Keep fallback mock data, but make it tenant-aware and clearly identify fallback behavior in logs or response metadata. This preserves demo resilience while preventing mock data from creating or hiding tenant leaks.
- Add explicit `month` and `year` query parameters to `/api/v1/dashboard/summary`. The frontend should default to March 2024 because the assignment's reported mismatch is March-specific.
- Return financial totals as decimal strings and format them in the frontend without JavaScript floating-point arithmetic as the source of truth.
- Add a small backend endpoint for tenant-scoped properties. The dashboard should fetch this list instead of hardcoding all properties in the frontend.
- Show the reporting period using property-local language, for example `March 2024, property local time`, so the timezone fix is visible during the walkthrough.

### Implementation Implications
- `backend/app/services/cache.py` should include `tenant_id`, `property_id`, `month`, and `year` in revenue cache keys.
- `backend/app/api/v1/dashboard.py` should validate `month` and `year`, pass them through to revenue services, and avoid converting totals to `float`.
- `backend/app/services/reservations.py` should calculate month boundaries using each property's timezone and query against UTC timestamps.
- Fallback data should be keyed by tenant and property, not property alone.
- `frontend/src/components/Dashboard.tsx` should fetch tenant-scoped properties and pass the selected property, month, and year to `RevenueSummary`.
- `frontend/src/components/RevenueSummary.tsx` should treat `total_revenue` as a string and display the selected period/local-time label.
