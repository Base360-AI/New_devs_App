## 1. Frontend test harness

- [x] 1.1 Add Vitest, React Testing Library, and a `test` script in `frontend/package.json`, then verify `npm test` runs from `frontend/`
- [x] 1.2 Add `frontend/tests/features/` plus a loader that discovers `.feature` files (or equivalently named Vitest files), then verify the runner reports zero scenarios until features are added

## 2. Isolation scenarios (red)

- [x] 2.1 Write Gherkin for authenticated-tenant revenue requests (tenant-a vs tenant-b `prop-001`, no default `candidate` header) and verify the new scenarios fail on the current `RevenueSummary` default
- [x] 2.2 Write Gherkin for tenant-scoped client caches (refresh after switch, two keys for shared `prop-001`) and verify they fail if the cache key omits tenant identity
- [x] 2.3 Assert captured `getDashboardSummary` URL and headers in those steps, then verify a failing test names the unscoped or `candidate` header

## 3. Timezone scenarios (red)

- [x] 3.1 Write Gherkin for profile-timezone display vs browser zone (America/New_York profile, Europe/Paris browser, UTC fallback) and verify the scenarios fail when display uses `Intl` browser TZ
- [x] 3.2 Write Gherkin for property-timezone March revenue (Paris `prop-001` includes `res-tz-1` at 2250.000 even if the user is New York) and verify they fail if the client rewrites the month with browser or profile TZ

## 4. Client fixes (green)

- [x] 4.1 Stop defaulting `debugTenant` to `candidate`; use session tenant for revenue fetches, then verify isolation request scenarios pass
- [x] 4.2 Include tenant identity in dashboard/revenue client cache keys and clear the previous tenant on switch, then verify cache isolation scenarios pass
- [x] 4.3 Render user-facing timestamps with profile timezone (UTC if missing) and keep month windows on property timezone, then verify timezone scenarios pass
- [x] 4.4 Run `npm test` in `frontend/` and verify the isolation plus timezone suites are green with no skipped scenarios
