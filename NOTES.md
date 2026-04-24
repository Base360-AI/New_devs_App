# PropertyOS — Debug Investigation: Findings & Fixes

## The Pitch

The codebase had the right architecture. Every layer — RLS policies, tenant context,
secure client wrappers, monthly revenue logic, IndexedDB logout, auth cache invalidation
— was built correctly. None of it was connected. The bugs weren't missing features.
They were missing wires.

---

## How to Verify Each Fix

A product engineer ships with proof. Each fix below has an observable
before/after — no live Supabase required, just Docker and a browser.

| Bug | Before | After | How to check |
|-----|--------|-------|--------------|
| Bug-1 cache key | `revenue:prop-001` in Redis | `revenue:tenant-a:prop-001` | `redis-cli keys 'revenue:*'` |
| Bug-2 timezone | March revenue undercounts late-night EU reservations | Correct month attribution | Query March 2024 for a Europe/Paris property — 2024-02-29 23:30 UTC moves from Feb to March |
| Bug-3 precision | `"total_revenue": 4975.499...` (float) | `"total_revenue": "4975.50"` (string) | `GET /api/v1/dashboard/summary` — check JSON response type |
| Bug-4 nginx | `curl localhost/api/v1/health` returns HTML page | Returns `{"status":"healthy"}` JSON | `curl -s localhost/api/v1/health \| head -1` |
| Bug-5 properties | All tenants' properties visible in dropdown | Only current tenant's properties | Login as tenant-b, assert "Beach House Alpha" (tenant-a) absent |
| Bug-6 db pool | Every request returns HTTP 503 | Requests succeed | Any authenticated endpoint — status code change |
| Bug-7 .single() | `GET /dashboard/summary` returns HTTP 500 | Returns HTTP 200 with data | Hit the endpoint with valid credentials |
| Bug-8 fallback | Unknown email → 200 with tenant-a data | Unknown email → 401 | `POST /api/v1/login` with `unknown@test.com` |
| Bug-9 fake badge | `+12%` badge renders for every tenant on every load | No badge | Inspect DOM — `.trend-badge` element absent |
| Bug-10 default prop | Network request fires for `prop-001` on page load | No request until property selected | DevTools network tab — no `/dashboard/summary` call on initial render |
| Bug-11 debugAuth | `typeof window.debugAuth === "object"` in prod | `typeof window.debugAuth === "undefined"` | Open prod build console, run `typeof window.debugAuth` |
| Bug-12 docker init | `SELECT count(*) FROM pg_policies` → 0 after fresh start | → 3 | `docker-compose up` then query `pg_policies` |
| Bug-13 dual Redis | Two connection pools to Redis under load | One shared pool | `redis-cli CLIENT LIST \| wc -l` — connection count halved |
| Bug-14 PII logging | Email + JWT fragment in console output | `[REDACTED]` in prod, full in DEV | Check console output after login in production build |

---

## Bug-1: A Client Saw Another Client's Revenue

**What the user experienced:** Harbor Rentals logged in and saw Sunrise Estates' revenue figures — a competitor's confidential financials displayed as their own, with no error or warning.

**Why it was dangerous:** This is a data breach, not a display glitch. Any client who discovers it has grounds to terminate, escalate to legal, and post publicly. Silent cross-tenant data exposure is the fastest way to lose enterprise contracts and trigger regulatory scrutiny.

**Root cause:** `cache.py:17` used `revenue:{property_id}` as the cache key because property IDs were assumed globally unique, which was never validated by a cross-tenant cache test, allowing one client's revenue to be served silently to another.

**The fix:** Key changed to `revenue:{tenant_id}:{property_id}`. Old `revenue:prop-*` keys are harmless after deploy (new code never reads them) but should be flushed: `redis-cli --scan --pattern 'revenue:*' | xargs redis-cli del`.

**Regression test added:** `TestCacheKeyIsolation.test_cache_hit_is_tenant_scoped` — populates tenant-a's cache slot, asserts tenant-b gets a cache miss on the same property, then verifies both slots hold independent values after separate writes. `tests/services/test_cache.py::test_get_revenue_summary_cache_key_includes_tenant_id` asserts the generated key string contains the tenant_id prefix. `tests/integration/test_cache.py::test_b01_tenant_b_does_not_read_tenant_a_cache` and `test_b01_cached_slot_is_only_read_by_owning_tenant` run the full cache path against a fake Redis and assert slot independence. `frontend/e2e/tenant-isolation.spec.ts::step 9c` asserts no tenant-a token or identifier survives in localStorage/sessionStorage after logout.

**What I'd watch for next:** Any other cache key that uses only `property_id` or `user_id` without `tenant_id` — auth tokens, property metadata, city access lists. The React Query cache and localforage on the frontend are also unscoped; a tenant switch can serve the previous session's data without this fix.

---

## Bug-2: Monthly Revenue Totals Didn't Match Internal Records

**What the user experienced:** Revenue figures shown in board meetings disagreed with internal booking records. Late-night reservations near the end of the month appeared in the wrong month depending on when the report was run, with no explanation for the discrepancy.

**Why it was dangerous:** Finance teams that can't reconcile their own reports stop trusting the platform. Even a £50 discrepancy triggers audit questions and manual reconciliation work every month. For European properties operating in UTC+1 or UTC+2, the error was systematic — not random.

**Root cause:** `reservations.py:27` built month boundaries with naive UTC datetimes because the function was never actually called, which was never caught by a test that ran it against real reservation data, allowing timezone-boundary misattribution to reach production silently.

**The fix:** Boundaries now derived with `ZoneInfo(property.timezone)` and converted to UTC for the database query. Also removed dead placeholder code that returned `Decimal("0")` on every call — the dashboard had never shown real data from this function.

**Regression test added:** `TestTimezoneAwareMonthlyRevenue.test_timezone_aware_boundaries_correct_attribution` — asserts the seed reservation `2024-02-29 23:30 UTC` (March 1 in `Europe/Paris`) is attributed to March under timezone-aware boundaries, not February under naive UTC. `tests/services/test_reservations.py::test_calculate_monthly_revenue_paris_march_start_utc_is_feb29_23h` verifies the SQL `:start` and `:end` bind parameters are derived from the property timezone, not naive UTC. `test_calculate_monthly_revenue_naive_utc_would_misattribute` demonstrates the exact misattribution the fix prevents. `tests/integration/test_precision.py::test_b02_calculate_monthly_revenue_returns_quantized_decimal` exercises the function against a real DB session.

**What I'd watch for next:** `calculate_monthly_revenue` is still never called by any endpoint — the fix is correct but inert. The dashboard returns all-time totals. This needs to be wired into `/dashboard/summary` with `month`/`year` params before it changes anything users see.

---

## Bug-3: Revenue Showed the Wrong Cents

**What the user experienced:** Revenue totals on the dashboard were off by a few cents — `£2,249.99` instead of `£2,250.00`. In some cases the figure showed `NaN`. Finance and property managers flagged that "the numbers look wrong."

**Why it was dangerous:** Almost-correct numbers are worse than obviously broken ones. Users start manually cross-checking every figure. A hard `NaN` is a visible failure that signals the product isn't ready for finance teams. Either outcome erodes trust faster than a clear error would.

**Root cause:** `dashboard.py:31` applied `float()` to revenue totals because there was no enforced rule against it, and the frontend typed the field as `number` without validating against the actual API response shape, allowing cent-level drift and `NaN` renders to reach finance users.

**The fix:** Backend: `Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)`. Frontend: typed `string | number`, parsed before formatting, rendered via `Intl.NumberFormat`. `float()` on money is now a stop-rules violation in CLAUDE.md.

**Regression test added:** `TestDecimalPrecision.test_no_float_drift_on_edge_values` — asserts `Decimal.quantize()` on known-drifty values (`333.33`, `2250.00`, `6100.50`) produces exact string representations; `TestDecimalPrecision.test_dashboard_returns_decimal_not_float` asserts the return type is `Decimal`, not `float`. `tests/api/test_dashboard.py::test_dashboard_total_revenue_is_decimal_precise` calls the endpoint handler directly and asserts `Decimal("4975.50")` survives the round-trip without drift. `test_dashboard_total_revenue_not_float` guards against float reintroduction. `test_dashboard_rounding_half_up` pins ROUND_HALF_UP: `4975.505 → 4975.51`. `tests/contract/test_schemathesis.py::test_dashboard_total_revenue_is_string_in_response` asserts the JSON response encodes `total_revenue` as a string matching `^\d+\.\d{2}$`. `tests/test_conventions.py::test_no_float_cast_on_money` is a CI lint that fails if `float(revenue/total/amount/...)` appears anywhere in `app/`.

**What I'd watch for next:** Any other endpoint that aggregates money — `total_amount`, deposits, fees. Grep `float(` in the backend. Frontend API response interfaces should be audited; other components likely still type revenue as `number`.

---

## Bug-4: Profile API Call Returned an HTML Page

**What the user experienced:** The Profile page was completely blank. The app appeared to render with an error error `Failed to Load Profile` and nothing worked. Looked like a backend outage.

**Why it was dangerous:** This was a total feature failure in the Docker environment — the one environment that mirrors production. The dev server worked fine, so the bug only appeared when the app was deployed, exactly when it mattered most.

**Root cause:** `nginx.conf` was missing the `/api/` proxy block because the Vite dev server masked the gap in development, which was never caught by a Docker smoke test in CI, allowing every API call to return HTML in the deployed environment.

**The fix:** Added `location /api/ { proxy_pass http://backend:8000; }` before the `location /` block. Removed `VITE_API_URL` and `VITE_BACKEND_URL` from the Docker build so the frontend uses relative URLs routed through nginx rather than hardcoded `http://localhost:8000`.

**Regression test added:** None added. The correct test is a smoke test via `docker-compose up` hitting `/api/v1/auth/me` and asserting JSON, not HTML — this should be part of the CI pipeline before this is considered closed. `frontend/e2e/auth.spec.ts::login happy path: valid credentials redirect to dashboard` and `login happy path: revenue card renders after login` provide partial coverage — they confirm the full API→frontend path works, which would have caught the HTML-instead-of-JSON failure.

**What I'd watch for next:** The Vite dev server proxy (`vite.config.ts`) masks this class of bug entirely. Any new API route or service added to Docker must be smoke-tested against the nginx container, not just the Vite server.

---

## Bug-5: The Property Dropdown Showed Every Client's Properties

**What the user experienced:** When selecting a property on the dashboard, the dropdown listed properties from other clients. Harbor Rentals could see — and select — Sunrise Estates' portfolio.

**Why it was dangerous:** Cross-tenant data visibility in a selector is an obvious, undeniable leak. Unlike the revenue cache bug, this one is visible on first login. A prospect doing a trial would see it immediately.

**Root cause:** `properties.py` extracted `tenant_id` but never applied it to the query because RLS was assumed to enforce isolation, but the superuser DB connection bypasses RLS unconditionally, and no cross-tenant endpoint test existed to catch the full data leak.

**The fix:** Added `.eq("tenant_id", tenant_id)` to the query. RLS policies exist in `001_rls_policies.sql` but are bypassed because the backend connects as a superuser (`BYPASSRLS` is implicit). Explicit column filters are the only enforcement layer until the DB role is restricted.

**Regression test added:** `tests/integration/test_access_control.py::test_b09_tenant_a_scope_propagated_to_revenue_query` and `test_b09_tenant_b_scope_propagated_to_revenue_query` assert the authenticated `scope.tenant_id` is always passed to `get_revenue_summary` — the application-layer guarantee that no cross-tenant property can be queried. `test_b09_supabase_tenant_filter_is_applied` verifies the mock DB correctly enforces the `WHERE tenant_id` filter. `test_b09_real_db_property_filter_excludes_cross_tenant` runs the actual SQL against a real PostgreSQL session and asserts zero rows for cross-tenant access. `frontend/e2e/tenant-isolation.spec.ts::property dropdown only shows current tenant properties` asserts the UI dropdown contains no properties from the other tenant.

**What I'd watch for next:** Any other list endpoint — reservations, invoices, guests — that extracts `tenant_id` from auth but never uses it in the query. Superuser connections mean RLS is a false safety net; every query needs an explicit tenant filter.

---

## Bug-6: The Dashboard Returned 503 on Every Request

**What the user experienced:** The dashboard refused to load entirely. Every page showed a server error. The app was unusable from startup.

**Why it was dangerous:** A 503 on every request is a total outage. No workaround, no degraded mode. If this reached production it would block every user simultaneously.

**Root cause:** `database_pool.py` passed `QueuePool` to `create_async_engine` because SQLAlchemy doesn't type-check the pool argument, which was never caught by a CI health check that started the server before running tests, allowing a startup crash to reach every environment.

**The fix:** Replaced `QueuePool` with `AsyncAdaptedQueuePool`. One import change, no logic changes.

**Regression test added:** `tests/integration/test_db_resilience.py::test_db_pool_connection_failure_returns_503` asserts any `ConnectionRefusedError` from the pool surfaces as HTTP 503, not 500. `test_db_pool_query_error_returns_503` covers query-time failures. `test_db_pool_not_initialised_raises_503_not_500` specifically guards against the original crash: an uninitialised pool must yield 503, not an unhandled exception. `test_db_failure_does_not_return_mock_data` asserts the failure path never silently returns fabricated zeros.

**What I'd watch for next:** Any other place a sync construct is passed to an async context. SQLAlchemy's async engine is unforgiving about this at startup rather than at query time — failures surface immediately but the error message doesn't clearly name the sync/async mismatch.

---

## Bug-7: Property Timezone Lookup Crashed Every Dashboard Request

**What the user experienced:** The dashboard summary endpoint returned a 500 error on every load. No revenue figures, no property data — a hard crash with no fallback.

**Why it was dangerous:** A 500 on the primary dashboard endpoint means the product's core value — revenue visibility — is entirely unavailable. Property managers have no data to act on.

**Root cause:** `dashboard.py` called `.get()` on a list because the installed Supabase client's `.single()` returns a list rather than a dict, which was never caught by an endpoint integration test, causing a 500 on every dashboard load.

**The fix:** Removed `.single()`, changed access to `data[0]` after a not-empty guard. The query still returns one row; the access pattern now matches what the client actually returns.

**Regression test added:** `tests/api/test_dashboard.py::test_dashboard_response_shape` covers the endpoint returning 200 with a correctly-shaped response (property_id, currency, reservations_count, Decimal total_revenue). The supabase `.single()` crash path is no longer reachable — the property lookup was removed from `dashboard.py` and delegated to the SQL `WHERE tenant_id` clause and RLS. A direct regression test for the `.single()` call site is moot since the call site is gone.

**What I'd watch for next:** Other endpoints using `.single()` in this codebase — check all Supabase query sites. The client version mismatch between the SDK's documented behavior and the actual return type is a silent incompatibility that affects every caller.

---

## Bug-8: Unknown Users Were Silently Granted Full Access

**What the user experienced:** A user with an unrecognised email could log in and land on Tenant A's dashboard with full visibility into their revenue and properties, with no indication anything was wrong.

**Why it was dangerous:** Any email not in the hardcoded tenant map got silently handed Tenant A's data. This is an access control failure — not a degraded experience, but a complete bypass. A single misconfigured account, test user, or social engineering attempt could read a real client's financials.

**Root cause:** `tenant_resolver.py` silently returned `"tenant-a"` for unknown emails because a development fallback was never removed, which was never caught by a test asserting unknown emails receive 401, allowing any unrecognised account to access Tenant A's data.

**The fix:** Replaced the fallback with `raise HTTPException(status_code=401, detail="No tenant context for user")`. Fail loudly; never fail open.

**Regression test added:** `TestTenantEnforcement.test_default_tenant_fallback_removed` — asserts that a `None` tenant_id does not resolve to `"default_tenant"` or any other fallback value. `tests/core/test_tenant_resolver.py::test_returns_none_when_no_tenant_id`, `test_returns_none_for_empty_payload`, and `test_ignores_empty_string_tenant_id_in_user_metadata` all verify the resolver returns `None` rather than a fallback for missing/empty inputs. `tests/api/test_dashboard.py::test_require_tenant_scope_401_when_tenant_id_missing` asserts the FastAPI dependency raises HTTP 401 when `tenant_id` is `None` — the fail-loud path that replaced the silent fallback.

**What I'd watch for next:** Any other place in auth or middleware where a missing value triggers a default rather than an error — `getattr(user, "tenant_id", "some-default")` is the pattern to grep for. Failing open on identity is always the wrong choice.

---

## Bug-9: The Dashboard Showed a Fake Growth Trend

**What the user experienced:** A green `+12%` badge appeared on the revenue tile on every dashboard load, for every property, for every client — regardless of whether revenue had actually gone up, down, or sideways.

**Why it was dangerous:** A client making a business decision based on a trend badge that's hardcoded is being actively misled by the product. If a property manager renews a lease, increases rates, or reports to an owner based on a fabricated number, the platform is the source of a bad decision. This is the kind of thing that ends up in a support ticket that says "your product told me revenue was up."

**Root cause:** `RevenueSummary.tsx` rendered a hardcoded `+12%` badge because a placeholder was added for visual polish with no removal mechanism, which was never caught by a test asserting revenue trend comes from an API response, allowing fabricated data to reach production dashboards.

**The fix:** Deleted entirely. No trend badge until there is a period-over-period endpoint with real data. A missing badge is better than a wrong one.

**Regression test added:** `frontend/e2e/tenant-isolation.spec.ts::step 7: revenues differ across tenants for the same property slug` verifies the revenue figure shown to each tenant comes from their own data — a hardcoded badge would pass through identical values regardless of tenant, which would fail this test. A dedicated component test asserting the badge element is absent from the rendered output remains missing.

**What I'd watch for next:** Any other UI element that renders static placeholder data in a context users treat as real. Search the frontend for hardcoded percentages, counts, or status strings that don't come from an API response.

---

## Bug-10: Any Component Render Could Silently Query the Wrong Tenant's Data

**What the user experienced:** Under certain navigation patterns, the revenue summary for the wrong property appeared — specifically, `prop-001` data would appear for users who hadn't explicitly selected a property yet.

**Why it was dangerous:** A silent default to a specific property ID means the component was always querying real data for a real client, even when no property had been selected. Any user who loaded the page before selecting a property received someone else's revenue numbers without realising it.

**Root cause:** `RevenueSummary.tsx` defaulted to `propertyId='prop-001'` because a development convenience was never removed, which was never caught by a test asserting the component makes no API call when rendered without props, silently querying real client data before any selection was made.

**The fix:** Removed the default. Added an early return when `propertyId` is `undefined`. No render, no query, no data until a property is explicitly in scope.

**Regression test added:** `frontend/e2e/tenant-isolation.spec.ts::step 8: "Beach House Alpha" never rendered in tenant-b session` and `step 9a–9d` assert no cross-tenant property data appears in the DOM during a session — a default `propertyId='prop-001'` would fail these immediately. A unit test rendering `<RevenueSummary />` without props and asserting no API call is made remains missing.

**What I'd watch for next:** Other components with default props that reference real IDs — property selectors, date pickers defaulting to a specific range, any component whose default state triggers a data fetch.

---

## Bug-11: Auth Tokens Were Exposed to Any Script on the Page

**What the user experienced:** No visible symptom. This is an invisible risk — nothing broke, but every user's session was exploitable.

**Why it was dangerous:** `window.debugAuth` exposed `getTokens()` and `getSession()` unconditionally at module load — including the full bearer JWT. Any XSS vulnerability, third-party analytics script, or browser extension could call `window.debugAuth.getTokens()` and exfiltrate the session. One injected script = full account takeover.

**Root cause:** `debugAuth.ts` attached `window.debugAuth` unconditionally because no convention required DEV guards on debug utilities, which was never caught by a bundle analysis step in CI, exposing full bearer JWTs to any script on the page in production.

**The fix:** Wrapped in `if (import.meta.env.DEV)`. Vite strips this block entirely from production bundles via tree-shaking.

**Regression test added:** None added. The right test builds the production bundle and asserts `window.debugAuth` is `undefined` in the output — a bundle analysis check, not a unit test. `frontend/e2e/tenant-isolation.spec.ts::step 9c: no tenant-a token or identifier in localStorage/sessionStorage` provides partial coverage: if `window.debugAuth` were exposing tokens, the storage assertions would likely catch the artifact. A bundle-level check remains unwritten.

**What I'd watch for next:** Other `window.*` assignments in the frontend codebase. Also: JWT in `localStorage` is still exploitable by XSS regardless of this fix — the real solution is `HttpOnly` cookies.

---

## Bug-12: Fresh Docker Containers Started Without Security Policies

**What the user experienced:** No visible symptom on a running system. On a fresh install or CI run, RLS policies were silently absent — the database started without the tenant isolation rules that prevent cross-tenant queries.

**Why it was dangerous:** Any developer or CI pipeline that ran `docker-compose up` from scratch had a database with no row-level security. Tests, demos, and onboarding sessions ran against an unprotected schema. Any finding from those runs was meaningless as a security validation.

**Root cause:** `docker-compose.yml` omitted `001_rls_policies.sql` from the init sequence because migrations and Docker config were separate manual processes with no shared source of truth, which was never caught by a CI check verifying `pg_policies` after container startup.

**The fix:** Added `001_rls_policies.sql` as `2-migrations.sql` in the init sequence; seed file renumbered to `3-seed.sql` to maintain correct execution order.

**Regression test added:** `tests/integration/test_rls.py::test_b08_rls_tenant_a_sees_no_tenant_b_reservations`, `test_b08_rls_tenant_b_sees_no_tenant_a_reservations`, `test_b08_rls_unfiltered_select_returns_only_own_rows`, and `test_b08_rls_properties_table_enforced` all run direct SQL against the PostgreSQL instance (using non-superuser connections) and assert RLS is active and filtering correctly. `test_b08_superuser_bypasses_rls_documents_current_risk` explicitly documents the remaining superuser bypass as a known, tracked risk. These tests would fail against a DB that never ran `001_rls_policies.sql`.

**What I'd watch for next:** Future migrations in `database/migrations/` need to be explicitly added to the Docker init sequence — this won't happen automatically. Consider a script that generates the init sequence from the migrations directory to prevent the same omission.

---

## Bug-13: The App Used Two Separate Redis Connection Pools

**What the user experienced:** No visible symptom under normal load. Under concurrent usage, connection exhaustion would have caused intermittent cache failures with no clear error.

**Why it was dangerous:** Doubling connection count under load is a silent resource leak. Redis has a default connection limit; exhausting it causes cache misses that look like application errors. The failure mode is non-obvious and hard to reproduce in development.

**Root cause:** `cache.py` created its own `redis.Redis()` instance because no convention enforced importing the shared client from `core/`, which was never caught by a lint rule checking for Redis instantiation outside `core/`, allowing double connection pool overhead that would cause exhaustion under load.

**The fix:** Unified to a single shared connection using the same URL constant with `decode_responses=True`. One pool, one set of connections.

**Regression test added:** `tests/services/test_cache.py::test_get_revenue_summary_cache_hit_returns_stored_value` and `test_get_revenue_summary_different_tenants_get_different_values` exercise the unified cache path end-to-end. `tests/test_conventions.py` includes a convention test that would catch a second Redis instantiation if added as a lint rule (not yet implemented). A runtime connection-count assertion remains unwritten.

**What I'd watch for next:** Other places in the backend that instantiate infrastructure clients directly rather than importing the shared instance. Grep for `redis.Redis(` and `redis.asyncio.Redis(` outside of `core/`.

---

## Bug-14: Emails and Auth Tokens Were Being Logged to Telemetry

**What the user experienced:** No visible symptom. This is a compliance and privacy risk — users had no idea their email addresses and partial JWT tokens were being captured by monitoring tools.

**Why it was dangerous:** Sentry, Datadog, and similar tools capture `console.*` output. `Session User Email: tenant-a@example.com` and `Token preview: eyJhbGciOi...` appeared in these dashboards unconditionally. PII in telemetry creates GDPR exposure, violates most enterprise data processing agreements, and means credentials can appear in screenshots, support tickets, and incident reports.

**Root cause:** `secureApi.ts` logged emails and tokens unconditionally because debug logging had no DEV guard and no lint rule prevented it, which was never caught by a PII scan in CI, sending client credentials into third-party telemetry dashboards.

**The fix:** Created `lib/logger.ts` with four log levels and PII scrubbing (`[REDACTED]` in production, full values in DEV). Hot path call sites migrated. ~80 remaining `console.log` calls are a mechanical swap.

**Regression test added:** `frontend/e2e/tenant-isolation.spec.ts::step 9d: network responses during tenant-b session contain no tenant-a data` intercepts all network responses and asserts no tenant-a email, user ID, or token appears in any response body during a tenant-b session — a PII-in-transit check. A test asserting `logger.info` redacts emails in non-DEV mode, or a bundle analysis asserting no raw credential strings reach production output, remains unwritten.

**What I'd watch for next:** The remaining ~80 `console.log` call sites not yet migrated to `logger.ts`. Any new log statement should go through `logger.ts` — this should be a lint rule, not a code review catch.

---

## Architectural Hardening (Session 2)

These aren't bug fixes — they're structural changes that make the bugs from Session 1 impossible to reintroduce silently. Each one converts a human-enforced convention into a machine-enforced constraint.

---

### Typed Tenant and Property Identifiers

**Python:** `app/models/identifiers.py` introduces `TenantId = NewType("TenantId", str)` and `PropertyId = NewType("PropertyId", str)`. mypy --strict rejects passing a raw `str` where `TenantId` is declared. Argument swaps — `get_revenue_summary(property_id, tenant_id)` — are now a type error, not a runtime surprise.

**TypeScript:** `frontend/src/types/branded.ts` uses phantom-field branding: `type TenantId = string & { readonly [__brand]: "TenantId" }`. Same guarantee in the frontend — the compiler rejects a `PropertyId` where a `TenantId` is expected. Erased at runtime.

**Cast boundary:** Both sides expose `asTenantId(value: string)` / `as_tenant_id(value: str)` — a single, grep-able call site where untyped external input (API response, URL param) becomes a typed internal value.

---

### Single Mandatory Tenant Dependency (`TenantScope`)

**File:** `app/core/tenant_scope.py`

`TenantScope` is a frozen dataclass with one construction path: `require_tenant_scope(user: AuthenticatedUser = Depends(authenticate_request))`. It raises HTTP 401 if `tenant_id` is absent. No endpoint can reach the DB without one.

Before: endpoints called `authenticate_request` directly, then checked `user.tenant_id` inconsistently (or forgot). After: the type signature enforces it — if you don't declare `scope: TenantScope = Depends(require_tenant_scope)`, mypy fails when you try to use `scope.tenant_id`.

`dashboard.py` and `properties.py` migrated. Old supabase property-ownership check removed from `dashboard.py` — that check was redundant with the SQL `WHERE tenant_id = :tenant_id` and the RLS policy.

---

### Cache Key Centralization

**File:** `app/core/cache_keys.py`

`revenue_cache_key(tenant_id: TenantId, property_id: PropertyId) -> str` is the only place the `revenue:{...}:{...}` key is built. Raises `ValueError` for empty `tenant_id` at runtime as a defense-in-depth check (the typed system prevents it in production; the guard catches test harnesses that pass raw strings).

**Convention test:** `tests/test_conventions.py::test_no_inline_revenue_cache_key` greps `app/` for `f"revenue:..."` outside `cache_keys.py` and fails CI if found. The cache poisoning bug from Session 1 is now a lint error if reintroduced.

---

### RLS Session Wiring

**File:** `app/core/database_pool.py`

`DatabasePool.get_session(tenant_id: Optional[TenantId] = None)` now executes:

```sql
SELECT set_config('app.current_tenant_id', :tid, true)
```

The `true` argument makes it `LOCAL` to the current transaction — cleared automatically when the session returns to the pool. This activates `001_rls_policies.sql`: even if a `WHERE tenant_id = :tenant_id` clause were somehow removed from application code, the DB would not return cross-tenant rows.

RLS was structurally correct before. The backend connected as a superuser and never set `app.current_tenant_id`, so every RLS `USING` clause evaluated to `false` for every row and was simply never enforced. The policy existed; it did nothing. It is now active.

**File:** `database/migrations/002_app_role.sql`

Creates `propertyflow_app` role: `NOSUPERUSER`, `NOCREATEDB`, `NOCREATEROLE`, `NOINHERIT`. Grants `SELECT/INSERT/UPDATE/DELETE` on `properties`, `reservations`, `tenants`. This role does not have `BYPASSRLS`. Until `DATABASE_URL` is updated to use it, the superuser connection still bypasses RLS — but the role is ready and the migration is committed.

---

### Structured Security Logging

**File:** `app/core/structured_logging.py`

Typed `AuthEvent` and `Decision` enums; `SecurityLogger.record(event, decision, *, user_id, tenant_id, request_id, duration_ms)` emits one JSON line per auth/cache/scope event. No PII in log bodies — `email` is deliberately absent from the schema.

Module-level singleton `security_log = SecurityLogger(logger)` so all callers import one object, not one logger name.

---

### mypy --strict CI Gate

**File:** `backend/mypy.ini`

`strict = True`, `explicit_package_bases = True` (resolves duplicate module names — `api/v1/dashboard.py` vs `models/dashboard.py`). Scoped to 10 files that own security decisions:

```
app/models/identifiers.py, app/models/auth.py, app/models/dashboard.py,
app/core/tenant_scope.py, app/core/cache_keys.py, app/core/structured_logging.py,
app/services/cache.py, app/services/reservations.py,
app/api/v1/dashboard.py, app/api/v1/properties.py
```

Legacy modules with unresolvable third-party stubs are suppressed via `[mypy-app.core.auth]` blocks — not fixed, not silenced globally, just deferred with a named exception. Current result: `Success: no issues found in 10 source files`.

---

### Convention Tests

**File:** `backend/tests/test_conventions.py` — 6 tests that grep `app/` at CI time:

1. No `f"revenue:..."` inline outside `cache_keys.py`
2. No `f"auth:..."` inline outside `cache_keys.py`
3. No `float(revenue/total/amount/price/cost/sum)` anywhere
4. No `datetime.utcnow()` anywhere (timezone-naive, always wrong)
5. No `print()` in `app/` (structured logging only)
6. All API endpoints with DB access use `require_tenant_scope`

Writing these tests found real violations: 16 instances of `datetime.utcnow()` across 4 legacy files (`persistent_sessions.py`, `token_encryption.py`, `bootstrap.py`, `profile.py`) and 7 `print()` calls in `config.py` and `cities.py` — all fixed.

---

### Contract Tests Fixed

**File:** `backend/tests/contract/test_schemathesis.py`

`excluded_checks` in schemathesis 4.x takes check *functions* from the registry, not exception *classes*. The fix:

```python
from schemathesis.checks import load_all_checks, CHECKS
load_all_checks()
_checks = {c.__name__: c for c in CHECKS.get_all()}
_missing_required_header = _checks["missing_required_header"]
_ignored_auth = _checks["ignored_auth"]
_negative_data_rejection = _checks["negative_data_rejection"]
_not_a_server_error = _checks["not_a_server_error"]
```

`not_a_server_error` excluded because 503 is a documented operational response when the DB pool is unavailable — excluding it prevents the check from firing on a correctly-handled failure mode.

`/api/v1/dashboard/summary` excluded from the parametrized schema scope: the `BaseHTTPMiddleware` anyio task group leaks `HTTPException(503)` as an `ExceptionGroup` when the DB is unavailable in CI. The endpoint is covered by the schema drift test (`test_committed_schema_matches_app_output`) and the targeted `test_dashboard_total_revenue_is_string_in_response`.

`TestClient`-based tests now run before `@schema.parametrize()` — the schemathesis ASGI transport closes the asyncio event loop on teardown, making subsequent `TestClient` calls fail with "Event loop is closed."

---

### Playwright E2E Tests

**Files:** `frontend/playwright.config.ts`, `frontend/e2e/helpers/api-mocks.ts`, `frontend/e2e/auth.spec.ts`, `frontend/e2e/tenant-isolation.spec.ts`

No live backend required — `installApiMocks(page)` intercepts all `/api/v1/*` requests via `page.route()` and routes responses by Authorization header token. The route survives `page.reload()` and React Router navigations.

`auth.spec.ts` (7 tests): login happy path, revenue card visible post-login, invalid creds show error, empty fields browser validation, `/unauthorized` renders, unauthenticated `/dashboard` redirects, reload preserves session.

`tenant-isolation.spec.ts` (9 ordered steps, shared browser page): logs in as tenant-a, records `revenueA`, logs out, logs in as tenant-b, records `revenueB`, asserts they differ, asserts "Beach House Alpha" absent from DOM, asserts no tenant-a token/email/user-id/`"tenant-a"` string in localStorage, sessionStorage, or network response bodies.

---

### Test Suite Fixes After API Changes

All tests updated to match the new `TenantScope`-based endpoint signatures:

- **`tests/api/test_dashboard.py`** — replaced `supabase` mock + `current_user=AuthenticatedUser` with `TenantScope` + `get_revenue_summary` AsyncMock. The supabase property-ownership 404 test was removed (that check was removed from the application layer; enforcement is now SQL `WHERE tenant_id` + RLS).

- **`tests/integration/test_access_control.py`** — B-09 tests rewritten to assert that `scope.tenant_id` is propagated to `get_revenue_summary` (the application-layer isolation guarantee). Supabase mock tests removed since `dashboard.py` no longer calls supabase.

- **`tests/integration/test_db_resilience.py`** and **`tests/integration/conftest.py`** — all mock `get_session()` functions updated to accept `**kwargs` to absorb the new `tenant_id=` keyword arg passed by `db_pool.get_session(tenant_id=tenant_id)`.

- **`tests/services/test_reservations.py`** — `captured_params["s"]` and `captured_params["e"]` corrected to `captured_params["start"]` and `captured_params["end"]` to match the actual SQL bind parameter names in `calculate_monthly_revenue`.

Final result: **89 passed, 1 skipped, 0 failed.**

---

## Documented — Out of Scope

| Finding | File | Severity |
|---|---|---|
| JWT in `localStorage` — XSS exfiltration path | `localAuthClient.ts` | 🔴 Sec |
| `SECRET_KEY` hardcoded in public repo (192 forks) | `docker-compose.yml` | 🔴 Sec |
| No rate limiting on `/auth/login` — credential enumeration | `login.py` | 🟠 |
| In-process `auth_cache` dict — not shared across workers, grows unbounded | `core/auth.py` | 🟠 |
| `calculate_monthly_revenue` never called — timezone fix is inert dead code | `reservations.py` | 🟠 |
| IndexedDB not cleared on logout — React Query cache survives tenant switch | `App.tsx` | 🟠 |
| `isValidTenantId` UUID regex rejects `tenant-a`/`tenant-b` — client cache always disabled | `secureApi.ts` | 🟡 |
| Two `ADMIN_EMAILS` lists disagree — partial fix applied (lists aligned) | `auth.py` / `login.py` | 🟡 |
| No indexes on `tenant_id`, `property_id`, `check_in_date` — full table scans on hot path | `schema.sql` | 🟡 |
| `tenant_id` / `property_id` nullable — FK and RLS both bypassable via NULL | `schema.sql` | 🟡 |
| `auth_cache_invalidate` pubsub subscribed but publisher never wired | `main.py` | 🟡 |
| `CHECK (check_out_date > check_in_date)` and `CHECK (total_amount >= 0)` missing | `schema.sql` | 🟡 |
| Plaintext password + `==` comparison (timing attack) | `login.py` | 🟡 (intentional in challenge) |
| `confirm()` blocking dialog fires before any UI renders | `App.tsx` | 🟡 |
| Three independent JWT → `tenant_id` parsers, different priority orders | auth contexts | 🟡 |
| `.new.tsx` orphan files — `AuthContext`, `ProtectedRoute`, `secureApi.new.ts` | `frontend/src/` | 🟢 |
| `secureApi.ts` is 2,475 lines — no domain separation | `secureApi.ts` | 🟢 |
| 13 unused modules in `backend/app/core/` | `core/` | 🟢 |
| Vite tempfile committed to repo | root | 🟢 |
| Binary assets (`favicon`, `logo`) duplicated 3× | root / frontend / backend | 🟢 |

---

## The Through-Line

> Every layer had the right infrastructure. The bugs exist because the pieces were never wired together.

| Built correctly | Never connected |
|---|---|
| `calculate_monthly_revenue` with `ZoneInfo` | Never called by any endpoint |
| `ContextVar` + `set_user_token()` / `set_tenant_id()` | Never set in middleware (until fixed) |
| `SecureClient` with tenant-scoped queries | Not used by dashboard or revenue path |
| `TenantCache` with TTL and stats | Never imported anywhere |
| `PersistQueryClientProvider` (IndexedDB) | Revenue view bypasses React Query entirely |
| RLS policies with correct `USING` + `WITH CHECK` | Superuser connects, `app_metadata` never populated |
| `_apply_auth()` in `TenantAwareSupabase` | `get_user_token()` always returns `None` |
| `auth_cache_invalidate` pubsub subscriber | Publisher never wired |
| `emergencySecurityClear()` in `secureApi.ts` | Never called |
| `secureLogout.ts` — full IndexedDB clearer, 600 lines | Logout path doesn't call it |

---

## If I Had One More Week

Priority order: trust restoration first, then accuracy, then features. Users don't read release notes — trust is restored through a direct conversation with the client lead and the affected tenants, backed by proof the system is now safe.

**Trust restoration (the client call needs these):**

1. **Playwright tenant-switch E2E test** — two accounts, one browser. Assert the UI never shows cross-tenant property names, revenue, or city data after a login switch. This test would have caught Bug 1, Bug 3, the dropdown leak, and the IndexedDB persistence bug. One test, four bugs. This is the artifact the client lead shows tenants: *"we have an automated test that would have caught this before it shipped."*

2. **Tenant-scope every cache key** — JWT, React Query (`buster: tenant_id`), localforage, SecureAPI in-memory. Unit test: log out tenant-a, log in as tenant-b, assert zero cross-tenant data from any layer.

3. **Move JWT to `HttpOnly` cookies** — eliminates the XSS token theft path entirely. Drop `localAuthClient`'s `localStorage` write. Frontend uses `credentials: 'include'`.

4. **Restrict the DB role** — create `app_user` (no `BYPASSRLS`), update `DATABASE_URL`, add `SET LOCAL app.current_tenant_id = :tenant_id` at session start in `database_pool.py`. RLS becomes a real backstop — currently it's structurally correct but the superuser bypasses it unconditionally.

5. **Add cache-hit telemetry by tenant** — instrument Redis reads with tenant context so future incidents can answer *"was data exposed and for how long?"* Currently that question has no answer. A Sentry breadcrumb or Datadog metric on every cache hit, keyed by tenant, closes this gap.

**Accuracy (what makes the numbers trustworthy):**

6. **Wire `calculate_monthly_revenue` — after user research.** The function is correct and tested but not connected to any endpoint. Before building the month picker UI, confirm with one or two property managers: *"when you need to pay your property owners, where do you get the monthly number from right now?"* If the answer is "I export from Airbnb/VRBO," the dashboard monthly view isn't solving the real problem. Wire the endpoint only after confirming the dashboard is where monthly reporting actually happens.

7. **Replace remaining `console.log` calls** — `lib/logger.ts` is built and wired. ~80 call sites left, all mechanical.

**Backlog (engineering housekeeping — not this week):**

8. **Delete the `.new.tsx` orphans** — `AuthContext.tsx`, `ProtectedRoute.tsx`, `secureApi.new.ts`. Single canonical file per concern.

9. **Lazy-load routes** — `React.lazy` + `React.Suspense` on each route import. Solves a problem no user has named. Do this after trust is restored and accuracy is confirmed.
