# PropertyOS — Postmortems

> Engineer's voice. Internal doc. Impact first, technical cause second.
> Each entry follows the same structure: opening sentence → what the user lived through → why it happened → why we didn't catch it → what changed → what makes it impossible to repeat.

---

## PM-1: A Client Saw Another Client's Revenue
**Date:** 2026-04-18 | **Severity:** P0 — Data Breach

> *"When two clients share a property ID, the revenue dashboard silently serves one client's financial data to the other — with no error, no log, and no way for either party to know it happened."*

**Impact**
Harbor Rentals logged in on a Monday morning and saw Sunrise Estates' revenue figures on their own dashboard. Not an error screen — their own dashboard, their own property, confidently displaying the wrong company's money. They'd have assumed it was their data. If they caught it — by noticing a figure that looked off, or by a coincidence that let them compare — the first reaction is shock, then dread: *if I can see theirs, they can see mine*. That's not a support ticket. That's a lawyer and a GDPR subject access request. That's a Trustpilot review that other prospects read before signing. That's the end of both contracts, not one.

**Cause**
`cache.py:17` used `revenue:{property_id}` as the cache key, assuming property IDs were globally unique — but `prop-001` is shared across tenants by design, so tenant-b's first dashboard load hit tenant-a's cached revenue and returned it as its own.

**Why it wasn't caught**
Every test used a single tenant. No test logged in as two different tenants, hit the same property, and checked that the cached values were independent. The cache key schema had no tenant scope, and there was no architectural constraint that would have made a non-tenant-scoped key fail to compile, lint, or test. The bug was writeable, testable, and deployable with nothing stopping it.

**Fix**
Cache key changed to `revenue:{tenant_id}:{property_id}`. Old `revenue:prop-*` keys are inert after deploy — new code never reads them — but should be flushed on deploy: `redis-cli --scan --pattern 'revenue:*' | xargs redis-cli del`.

**Prevention**
- **Test:** `TestCacheKeyIsolation.test_cache_hit_is_tenant_scoped` — populates tenant-a's slot, asserts tenant-b gets a cache miss on the same property, then verifies both slots hold independent values. This test would have blocked the original commit.
- **Convention:** Every cache key must include `tenant_id` as the first segment. Any key that doesn't — `revenue:{property_id}`, `session:{user_id}` — is a cross-tenant leak waiting for a shared ID.
- **CI gate:** A test that logs in as two tenants and asserts their dashboard responses are different objects. One test, blocks this entire class of bug for every cache layer in the system.

---

## PM-2: Monthly Revenue Totals Didn't Match Internal Records
**Date:** 2026-04-18 | **Severity:** High — Financial Accuracy

> *"When a property operates in a non-UTC timezone, the monthly revenue total misattributes reservations that fall near midnight to the wrong month — causing official reports to disagree with internal booking records without explanation."*

**Impact**
A property manager in Paris prepares her February revenue summary for a board meeting. The dashboard says £8,400. Her own records say £8,450. The discrepancy is £50 — small enough that she almost lets it go, large enough that she can't. She runs the report again. Same number. She checks the bookings manually. The numbers still disagree. Now she doesn't trust the platform, not just the one number. Every figure on the dashboard is suspect. Every month going forward requires manual reconciliation. The cost isn't £50 — it's the hours of cross-checking every reporting cycle and the slow erosion of confidence that leads to a churn conversation at renewal.

**Cause**
`reservations.py:27` built month boundaries with naive `datetime(year, month, 1)` — no timezone — treating UTC midnight as local midnight for every property regardless of where it operates. A reservation at `2024-02-29 23:30 UTC` is March 1 in `Europe/Paris`, but the query assigned it to February.

**Why it wasn't caught**
The function was dead code — it returned `Decimal("0")` on every call and was never wired to any endpoint. The timezone bug existed in code that had never executed in any environment. No test ran `calculate_monthly_revenue` with real reservation data. No integration test compared the endpoint's monthly total against a known seed row. A function can be wrong for months and never be discovered if nothing calls it.

**Fix**
Boundaries now derived with `ZoneInfo(property.timezone)` and converted to UTC for the database query. Dead placeholder code returning `Decimal("0")` removed. The fix is correct — but `calculate_monthly_revenue` is still not wired to any endpoint. The dashboard returns all-time totals. This needs `month`/`year` params on `/dashboard/summary` before it changes anything a user sees.

**Prevention**
- **Test:** `TestTimezoneAwareMonthlyRevenue.test_timezone_aware_boundaries_correct_attribution` — seeds `res-tz-1` at `2024-02-29 23:30 UTC` for a `Europe/Paris` property and asserts it falls in March, not February. A boundary reservation that changes month depending on whether you're naive or timezone-aware.
- **Convention:** Any function that takes a `month`/`year` pair must accept a `timezone` argument. A monthly boundary without a timezone is always wrong for someone.
- **CI gate:** Wire `calculate_monthly_revenue` to the endpoint with a `month`/`year` param, then add an integration test that seeds a known reservation and asserts the correct monthly total. Until this is done, the fix is inert.

---

## PM-3: Revenue Showed the Wrong Cents
**Date:** 2026-04-18 | **Severity:** Medium — Financial Accuracy / Display Failure

> *"When the backend serialises revenue totals, floating-point arithmetic introduces cent-level errors before the value reaches the client — and the frontend renders those corrupted values as NaN for any finance user viewing the dashboard."*

**Impact**
Two failure modes, different kinds of bad. The first: a property manager sees £2,249.99 instead of £2,250.00. She notices. She asks the team. Nobody can explain it. The number is almost right, which is worse than wrong — almost right means the logic ran, the data is real, but something in the pipeline is quietly losing precision. She stops trusting every figure and starts checking them manually. The second: a different user sees NaN. That's a hard failure. The product looks unfinished. No amount of explaining "it's a serialisation edge case" recovers the impression that the platform can't display money correctly.

**Cause**
`dashboard.py:31` applied `float()` to a Decimal revenue string — IEEE 754 drift turned `2250.00` into `2249.9999...` before serialisation. The frontend compounded this by typing revenue as `number`; when the API returned a Decimal string, `.toFixed(2)` on a string produced `NaN`.

**Why it wasn't caught**
No test asserted exact cent-level output at the endpoint boundary. No test checked the serialised value as a string. The frontend typed the field independently of the backend's actual response shape — no shared contract, no generated types, no test that deserialised a real response and checked the rendered value. Two independent assumptions about the same field, both wrong, with no meeting point between them.

**Fix**
Backend: `Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)` — exact, controlled rounding, no float conversion. Frontend: typed `string | number`, parsed with `parseFloat` before display, rendered via `Intl.NumberFormat`. `float()` on money is now a stop-rules violation in CLAUDE.md.

**Prevention**
- **Test:** `TestDecimalPrecision.test_no_float_drift_on_edge_values` asserts known-drifty values (`333.33`, `2250.00`, `6100.50`) survive the pipeline as exact strings. `test_dashboard_returns_decimal_not_float` asserts the return type is `Decimal`, not `float`.
- **Convention:** `float()` on any value that represents money is prohibited. `Decimal.quantize(TWOPLACES, ROUND_HALF_UP)` is the only path from database to wire.
- **CI gate:** Generate TypeScript types from the OpenAPI schema. A `total_revenue: number` type in the frontend would fail the schema check as soon as the backend declares it `Decimal` (string). One contract, one source of truth.

---

## PM-4: Every API Call Returned an HTML Page
**Date:** 2026-04-18 | **Severity:** P0 — Total Deployment Failure

> *"When a client opens the app for the first time outside a developer's laptop, every page that loads data shows an error — profile, revenue, properties — because the server is returning a blank page instead of responding to any API call. The app looks broken. It is broken. The developer's machine works fine."*

**Impact**
The app loads. The UI renders. And then nothing works. Profile page: blank. Revenue summary: blank. Every network call in the browser returns `<!DOCTYPE html>`. The backend shows no errors because no request ever reaches it. The developer runs the same app with `npm run dev` and everything works perfectly. The Docker deployment — the one that mirrors production, the one that matters — is completely broken. The gap between dev and Docker is invisible until the moment it isn't, which is usually a demo, a deploy, or a client onboarding call.

**Cause**
`nginx.conf` had no `location /api/` proxy block. The `try_files $uri $uri/ /index.html` catch-all intercepted every API call and returned `index.html`, causing `response.json()` to throw `Unexpected token '<', "<!DOCTYPE "... is not valid JSON`.

**Why it wasn't caught**
The Vite dev server has its own proxy configuration in `vite.config.ts` that correctly forwards `/api/` calls to the backend. It works. It's tested. It gives developers confidence. It hides the nginx configuration entirely. No one tested the Docker path in CI — no smoke test started the container and hit an API endpoint. Two proxy configurations existed in parallel, one correct and one broken, with nothing to compare them.

**Fix**
Added `location /api/ { proxy_pass http://backend:8000; }` before the `location /` block. Removed `VITE_API_URL` and `VITE_BACKEND_URL` from the Docker build environment so the frontend uses relative URLs routed through nginx, not hardcoded `localhost:8000`.

**Prevention**
- **Test:** A CI smoke test that runs `docker-compose up`, waits for healthy, sends `GET /api/v1/auth/me`, and asserts `Content-Type: application/json` — not `text/html`. This test would have caught the original omission and will catch any future nginx regression.
- **Convention:** The Vite dev proxy and the nginx config must be kept in sync. Any new service or API path added to `vite.config.ts` proxied routes must be mirrored in `nginx.conf` in the same PR.
- **CI gate:** Docker smoke test runs before any other test suite. If the container doesn't serve JSON from `/api/`, the build fails before unit tests run.

---

## PM-5: The Property Dropdown Showed Every Client's Properties
**Date:** 2026-04-18 | **Severity:** P0 — Data Leak / Visible on First Login

> *"When any authenticated user opens the property selector, the dropdown lists every property from every client — exposing a competitor's full portfolio on the first page of the application."*

**Impact**
Unlike the revenue cache bug, this one doesn't require a timing coincidence — it's visible on first login, every time, for every user. Harbor Rentals opens the property dropdown and sees Sunrise Estates' portfolio listed alongside their own. Property names, addresses, identifiers — a competitor's full asset list, served without restriction. A prospect doing a trial sees it in the first thirty seconds. There's no way to explain this as a display glitch. It's a raw data exposure and it reads that way immediately.

**Cause**
`properties.py` extracted `tenant_id` from the auth token but never applied it to the database query. No `.eq("tenant_id", tenant_id)` filter. Every row in the properties table was returned to every authenticated user.

**Why it wasn't caught**
RLS policies in `001_rls_policies.sql` exist and are structurally correct. The developer assumed they would enforce isolation automatically. They don't — the backend connects as a PostgreSQL superuser, and superusers have implicit `BYPASSRLS`. The policies were written but never effective. No test queried the properties endpoint as two different tenants and compared the result sets. RLS was a false safety net that everyone assumed was load-bearing.

**Fix**
Added `.eq("tenant_id", tenant_id)` to the properties query. This is now the only real enforcement layer — RLS won't enforce until the DB connection role is restricted to a non-superuser.

**Prevention**
- **Test:** An integration test that authenticates as tenant-b and asserts `GET /api/v1/properties` returns zero tenant-a properties. Apply this pattern to every list endpoint.
- **Convention:** Every list query that touches tenant-owned data must have an explicit `.eq("tenant_id", tenant_id)` filter. Trusting RLS with a superuser connection is trusting a lock that doesn't exist.
- **CI gate:** Restrict the DB role to a non-superuser `app_user` (no `BYPASSRLS`). Until then, the cross-tenant endpoint test is the only gate. Any PR touching a list endpoint must include a cross-tenant test to pass CI.

---

## PM-6: The Dashboard Returned 503 on Every Request
**Date:** 2026-04-18 | **Severity:** High — Total Outage on Startup

> *"When the application starts, the async database engine fails to initialise and returns 503 on every request — blocking all users before any business logic is reached, with no degraded mode or fallback."*

**Impact**
The application starts. Every request returns 503. Not a slow degradation, not an intermittent failure — a hard wall from the first request. No user gets past it. The logs show an engine initialisation error that references `QueuePool` and async compatibility, which means nothing to anyone who hasn't worked with SQLAlchemy's async internals before. The on-call engineer is debugging a configuration mismatch while users see a dead app. There is no workaround. The fix is a one-line import change, but you have to know what you're looking for first.

**Cause**
`database_pool.py` passed `QueuePool` (synchronous) to `create_async_engine`. SQLAlchemy's async engine rejected it at startup — the pool never initialised, and every subsequent request failed before reaching any route handler.

**Why it wasn't caught**
No CI step started the server and checked that it was healthy before running tests. Unit tests mock the database and never exercise the pool initialisation path. SQLAlchemy doesn't raise a type error at the call site — the wrong pool type is accepted at construction time and only fails at runtime. The mismatch was undetectable without actually starting the process.

**Fix**
`QueuePool` → `AsyncAdaptedQueuePool`. One import, no logic changes.

**Prevention**
- **Test:** A startup health check test that starts the application, waits for the pool to initialise, and asserts `GET /health` returns 200. Any startup-time misconfiguration — pool type, connection string, missing env var — would fail here.
- **Convention:** Async engine creation must use `AsyncAdaptedQueuePool` or `NullPool`. Document this in `database_pool.py` — the error message from the wrong choice is not self-explanatory.
- **CI gate:** Health check runs as the first CI step, before unit tests. A server that can't start should fail CI immediately, not after every unit test passes.

---

## PM-7: Property Timezone Lookup Crashed Every Dashboard Request
**Date:** 2026-04-18 | **Severity:** High — Complete Feature Unavailability

> *"When the dashboard loads, a type mismatch in the property query raises an unhandled AttributeError and returns 500 — making revenue data completely unavailable to every user on every request."*

**Impact**
Property managers open the dashboard to check their morning numbers and see a 500 error. Every time. For every property. The core product — the revenue summary that is the reason clients pay for the platform — doesn't load. There's no fallback, no cached view, no degraded state. The page is just broken. Support tickets arrive. The engineering team is debugging a Supabase client version mismatch while clients are unable to do their jobs.

**Cause**
`dashboard.py` called `.single()` on the property query expecting a dict, but the installed version of the Supabase client returns a list. `.get("timezone")` on a list raises `AttributeError`, which propagated as an unhandled 500.

**Why it wasn't caught**
No test hit `GET /dashboard/summary` end-to-end with a valid auth token and asserted a 200 response. The `.single()` return type disagreed with the SDK documentation, and no typed client was generated from the schema — the return type was assumed, not checked. A library version upgrade changed behaviour silently.

**Fix**
Removed `.single()`. Access changed to `data[0]` after a not-empty guard. The query still returns one row; the access pattern now matches what the installed client version actually returns.

**Prevention**
- **Test:** An endpoint integration test: authenticate, call `GET /dashboard/summary`, assert 200 and a non-empty `total_revenue` field. Any `.single()` → list regression breaks this immediately.
- **Convention:** Never assume Supabase client return types from documentation — verify against the installed version. Add a type stub or wrapper that asserts the return shape at the call site.
- **CI gate:** Lock the Supabase client version in `pyproject.toml`. Any version bump triggers a re-run of the endpoint integration test suite before merging.

---

## PM-8: Unknown Users Were Silently Granted Full Access to Tenant A
**Date:** 2026-04-18 | **Severity:** P0 — Access Control Bypass

> *"When a user with an unrecognised email logs in, the application silently assigns them to Tenant A's account — granting a stranger full read access to a real client's revenue, properties, and booking history."*

**Impact**
Any email not in the hardcoded tenant map returns the same experience: a fully functional dashboard, populated with Sunrise Estates' real financial data, with no indication that anything unusual has happened. A misconfigured test account, a social engineering attempt, a support engineer logging in with the wrong credentials — any of these land on a real client's data. The user doesn't know they're seeing the wrong account. The legitimate tenant doesn't know their data was accessed. There is no log of it happening.

**Cause**
`tenant_resolver.py` returned `"tenant-a"` as a silent fallback for any email not in the hardcoded lookup map. A development convenience — added so the app wouldn't break while the tenant map was being populated — was never removed and shipped as production auth logic.

**Why it wasn't caught**
No test sent a request with an unrecognised email and asserted the response was 401. Auth code was not treated as a security-critical path requiring explicit failure-mode coverage. Fail-open patterns in identity resolution are the most dangerous class of auth bug and the easiest to miss in review because the happy path works correctly.

**Fix**
Replaced the fallback with `raise HTTPException(status_code=401, detail="No tenant context for user")`. Unknown email → hard 401, always. No default, no silent assignment, no fallback tenant.

**Prevention**
- **Test:** `TestTenantEnforcement.test_default_tenant_fallback_removed` — sends a request with an email not in the tenant map and asserts 401. This test must pass for any auth middleware change to merge.
- **Convention:** Auth resolvers fail closed. `getattr(user, "tenant_id", "some-default")` is always wrong. Any fallback in an auth path is a security bug waiting for the right email address.
- **CI gate:** A security-path test suite that covers all auth failure modes — unknown tenant, missing JWT, expired token, wrong tenant — runs on every PR that touches `auth.py`, `tenant_resolver.py`, or any middleware file.

---

## PM-9: The Dashboard Showed a Fake Growth Trend
**Date:** 2026-04-18 | **Severity:** High — Misleading Financial Data

> *"When any property manager views the revenue dashboard, a hardcoded green +12% growth badge appears regardless of actual performance — actively misleading clients who use it to make pricing and leasing decisions."*

**Impact**
A property manager sees a green +12% badge every time she opens the dashboard. Revenue is up. She raises rates. She renews two leases at a premium. She reports to the property owner that performance is strong. Six weeks later, during a quarterly review, she pulls the actual booking data and discovers revenue was flat — possibly down. The badge was always +12%, for every client, in every market, in every month. It was never connected to anything real. The platform didn't just show her wrong data — it confidently showed her wrong data in the most prominent position on the most important page. That's not a bug. That's a liability.

**Cause**
`RevenueSummary.tsx` rendered a hardcoded `+12%` value unconditionally. The comment in the code: `{/* Fake trend indicator for premium feel */}`. No feature flag. No DEV guard. No TODO ticket. No linked issue. It shipped as-is.

**Why it wasn't caught**
No test verified that UI metric displays come from an API response. No policy existed requiring display elements showing business figures to have a traceable data source. Placeholder UI was added, looked good in design review, and was never removed because there was no mechanism to require its removal.

**Fix**
Deleted entirely. A missing badge is better than a wrong one. The badge comes back only when a period-over-period endpoint exists with real data behind it.

**Prevention**
- **Test:** A component test that renders `<RevenueSummary>` with a mock API response and asserts the trend value matches the response field — not a constant. Any hardcoded metric value fails this test by definition.
- **Convention:** No UI element that displays a business metric may render a static value. If the data source doesn't exist yet, the element doesn't exist yet.
- **CI gate:** A lint rule or component test pattern that flags any JSX rendering a numeric or percentage literal outside of a test file. Hardcoded business metrics are always wrong.

---

## PM-10: Revenue Summary Queried the Wrong Property Before Any Selection
**Date:** 2026-04-18 | **Severity:** Medium — Silent Cross-Tenant Data Access

> *"When the revenue summary component renders before a property is selected, it silently fetches and displays prop-001's data — showing a real client's financial figures to a user who has not yet chosen a property."*

**Impact**
A user opens the dashboard. Before they've selected anything, the revenue summary loads — and it's showing numbers. Real numbers. Just not their property's numbers. If both clients have similar revenue ranges, nobody notices. If the numbers look right — which they might, especially early in the day — the user might act on them. Report them. Screenshot them. The component was never in a "waiting for input" state. It was always in a "fetching prop-001" state, quietly, for every user.

**Cause**
`RevenueSummary.tsx` had `propertyId = 'prop-001'` as a default prop — a real production property ID hardcoded as a development convenience that was never removed.

**Why it wasn't caught**
No test rendered the component without a `propertyId` prop and asserted that no API call was made. The development environment always passed a property ID, so the default was never exercised. The component's "no selection" state was undefined behaviour that defaulted to fetching real data.

**Fix**
Default removed. Early return added when `propertyId` is `undefined`. No prop → no render → no query → no data. The component is now silent when it has nothing to display.

**Prevention**
- **Test:** Render `<RevenueSummary />` without any props and assert zero network calls and no revenue figure in the output. Any default that triggers a fetch fails this immediately.
- **Convention:** Components that fetch data must require their data-scope prop explicitly — no defaults that reference real IDs. If a component doesn't know what to show, it shows nothing.
- **CI gate:** A linting rule that flags default prop values containing string patterns that look like IDs (`prop-`, `tenant-`, `res-`). Development placeholders with real IDs are always wrong in production.

---

## PM-11: Auth Tokens Were Exposed to Every Script on the Page
**Date:** 2026-04-18 | **Severity:** High — Session Exfiltration Risk

> *"When the application loads in production, every user's full bearer JWT is attached to window.debugAuth — accessible to any JavaScript running on the page, including third-party scripts, browser extensions, and XSS payloads."*

**Impact**
Nothing visibly broken. That's what makes this dangerous. Every user's session was exploitable from the moment the page loaded, by anyone who knew to call `window.debugAuth.getTokens()`. A single XSS vulnerability anywhere in the application — a third-party analytics script with a supply chain issue, a malicious browser extension, a stored XSS in a property name field — becomes a full account takeover. The attacker gets the JWT, replays it, and has everything the legitimate user has. No user is alerted. No session is invalidated. The access looks identical to normal traffic.

**Cause**
`debugAuth.ts` attached `window.debugAuth = { getTokens, getSession, ... }` at module load with no environment guard — present in every production build, every time.

**Why it wasn't caught**
No convention required debug utilities to be wrapped in `import.meta.env.DEV`. No bundle analysis step checked for global `window.*` assignments in the production output. Code review caught functionality, not security surface area.

**Fix**
Wrapped in `if (import.meta.env.DEV)`. Vite tree-shakes the entire block from production bundles. In production, `window.debugAuth` is `undefined`.

**Prevention**
- **Test:** Build the production bundle and grep the output for `window.debugAuth`. Any match fails the build. This is a bundle analysis check, not a unit test — run it in CI as part of the build step.
- **Convention:** All `window.*` assignments that expose auth data or internal state must be wrapped in `import.meta.env.DEV`. No exceptions. Debug utilities added without this guard are security bugs.
- **CI gate:** A production build analysis step that scans for `window.debug`, `window.auth`, and `window.token` assignments in the built output. Runs on every PR that touches `src/utils/` or `src/lib/`.

---

## PM-12: Fresh Containers Started Without Security Policies
**Date:** 2026-04-18 | **Severity:** High — Schema Misconfiguration at Startup

> *"When a fresh Docker container starts, the database initialises without row-level security policies — running every developer environment, demo, and CI pipeline against a schema with no tenant isolation."*

**Impact**
No visible symptom on a running system. That's the problem. Every developer who cloned the repo and ran `docker-compose up` had a database without RLS. Every CI run, every demo, every onboarding session operated against an unprotected schema. When they ran the cross-tenant endpoint tests — the tests that check whether tenant isolation works — those tests were running against a database where the policies weren't there. Any passing result from those environments was meaningless. The security validation was testing a schema that didn't match production.

**Cause**
`001_rls_policies.sql` was written and committed to `database/migrations/` but never added to `docker-compose.yml`'s `docker-entrypoint-initdb.d` volume mount. Only `schema.sql` and `seed.sql` ran on container init.

**Why it wasn't caught**
Migrations and Docker init files were two separate manual processes with no shared source of truth and no automated sync. A migration could be written, committed, reviewed, and merged without ever being wired into the Docker environment. No CI step verified that the expected RLS policies existed in a freshly started container.

**Fix**
Added `001_rls_policies.sql` as `2-migrations.sql` in the init sequence. Seed file renumbered to `3-seed.sql` to maintain correct execution order.

**Prevention**
- **Test:** A CI step that starts the Docker container and runs `SELECT COUNT(*) FROM pg_policies WHERE tablename = 'reservations'`, asserting the expected policy count before any other test runs.
- **Convention:** Any new migration file added to `database/migrations/` must be wired into `docker-compose.yml` in the same PR. This should be a checklist item on the PR template.
- **CI gate:** Auto-generate the Docker init file list from the migrations directory in order. If the generated list doesn't match the committed list, the build fails. Eliminates the manual step entirely.

---

## PM-13: The App Used Two Separate Redis Connection Pools
**Date:** 2026-04-18 | **Severity:** Medium — Resource Exhaustion Under Load

> *"When the application starts, the cache layer creates a second independent Redis connection pool alongside the shared one — silently doubling connection overhead and creating a resource exhaustion risk that surfaces as intermittent failures under concurrent load."*

**Impact**
In development, with one or two users, nothing is wrong. In production, under concurrent load, Redis hits its default connection limit and starts refusing new connections. Cache misses start appearing — not consistently, not reproducibly, just intermittently. The application returns stale or empty data. The errors look like network issues or Redis instability. The actual cause — two pools competing for connections that should be shared — requires knowing that two separate `Redis()` instances were created in different modules. The debug trace is misleading, the fix is trivial, and the time between first symptom and correct diagnosis is entirely wasted.

**Cause**
`cache.py` instantiated `redis.Redis()` directly rather than importing the shared client from `core/redis_client.py`. Two pools, two connection budgets, both pointing at the same server.

**Why it wasn't caught**
No convention enforced importing the shared Redis client. No lint rule flagged `redis.Redis()` instantiation outside of `core/`. Infrastructure clients looked like library calls — not like things that needed to be singletons. Nobody grep'd for duplicate instantiations before shipping.

**Fix**
Unified to the shared `core/redis_client.py` client using the same URL constant with `decode_responses=True`. One pool.

**Prevention**
- **Test:** A startup assertion that queries Redis `CLIENT LIST` and asserts exactly one connection from the application process. Any duplicate pool instantiation adds a connection and fails this check.
- **Convention:** `redis.Redis()` and `redis.asyncio.Redis()` are only called in `backend/app/core/`. Every other module imports from there. This is an architectural boundary, not a style preference.
- **CI gate:** A ruff rule that flags any `redis.Redis(` or `redis.asyncio.Redis(` call outside of `backend/app/core/`. One rule blocks the entire class of duplicate instantiation.

---

## PM-14: Client Emails and Auth Tokens Were Logged to Telemetry
**Date:** 2026-04-18 | **Severity:** High — PII / GDPR Compliance Risk

> *"When the application runs in production, client email addresses and partial JWT tokens are logged unconditionally to console — appearing in Sentry, Datadog, and any other telemetry tool that captures console output."*

**Impact**
`Session User Email: tenant-a@example.com` and `Token preview: eyJhbGciOi...` appeared in the telemetry dashboard for every user session. Sentry and Datadog both capture `console.*` output. This means client emails and token fragments were in: every incident report, every support ticket with a session replay attached, every screenshot shared in a Slack thread, every Sentry issue linked to a stakeholder. Under GDPR, logging PII to a third-party processor without explicit consent and a DPA is a compliance violation. Under most enterprise contracts, it's a breach of the data processing agreement. The exposure wasn't a theoretical risk — it was happening on every login, every session, every day the application was running.

**Cause**
`secureApi.ts` and auth context files called `console.log` with email addresses and JWT fragments at module level, with no environment guard and no redaction — present in every production build.

**Why it wasn't caught**
Debug logging was treated as a development artifact that engineers would clean up before shipping. It wasn't. No lint rule flagged `console.log` calls containing auth-related variables. No PII scan ran in CI. No policy existed requiring log statements to go through a redacting logger. The assumption that debug logs stay out of production was wrong, and nothing enforced the right assumption.

**Fix**
Created `lib/logger.ts` with four log levels and PII scrubbing — `[REDACTED]` in production, full values in DEV. Hot path call sites migrated. ~80 remaining `console.log` calls are a mechanical swap.

**Prevention**
- **Test:** Build the production bundle, run it in a headless browser, and assert that no `console.log` output contains strings matching email or JWT patterns. Alternatively: a logger unit test asserting that `logger.info` in non-DEV mode redacts `@`-containing strings.
- **Convention:** All log statements go through `lib/logger.ts`. `console.log` is prohibited outside of test files. This should be enforced by a lint rule, not by code review.
- **CI gate:** An ESLint rule that flags `console.log`, `console.info`, and `console.debug` calls outside of test files and `logger.ts` itself. Any call with a variable named `email`, `token`, `jwt`, or `password` is a build failure regardless of location.
