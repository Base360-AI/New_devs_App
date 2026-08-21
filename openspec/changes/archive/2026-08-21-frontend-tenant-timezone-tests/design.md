## Context

See proposal.md for why. Backend isolation and property-timezone month windows are already locked by `backend/tests/features`. The dashboard UI has no test runner (`frontend/package.json` has no `test` script) and no `*.test.*` files.

Current constraints:

- `RevenueSummary` defaults `propertyId` to `prop-001` and `debugTenant` to `candidate`, then sends `X-Simulated-Tenant`.
- `SecureAPI.getDashboardSummary` only adds that header; tenant is not taken from the session JWT.
- Profile stores `timezone`; device analytics and session recovery use `Intl.DateTimeFormat().resolvedOptions().timeZone`.
- Client caches (`secureCache`, `tenantIsolatedStorage`, request cache in `secureApi`) exist but are untested against a shared `prop-001`.

## Goals / Non-Goals

**Goals:**

- Stand up a frontend test harness and write failing BDD-style scenarios first.
- Prove request identity, cache keys, profile-timezone display, and property-timezone March totals from the UI layer.
- Drive the smallest UI/client fixes those tests require.

**Non-Goals:**

- Replacing the backend suite or changing `month_bounds` / Redis key format.
- Full Playwright login against docker-compose (optional later; not required to close this change).
- Redesigning profile settings or adding new timezone pickers.

## Decisions

### 1. Vitest + Testing Library, Gherkin colocated with backend style

- **Choice**: Add Vitest (Vite-native) and React Testing Library. Put `.feature` files under `frontend/tests/features/` and step defs that assert fetch/cache/render behavior with mocked `SecureAPI`.
- **Why**: Matches the backend pytest-bdd workflow the team just used, without standing up a browser or API.
- **Alternative considered**: Playwright against `docker-compose`. Stronger end-to-end, but slow and blocked on auth/docker. Defer.
- **Alternative considered**: Jest. Extra runner next to Vite; Vitest is enough.

### 2. Two timezone clocks, never mixed

- **Choice**: User-visible timestamps use profile timezone (fallback UTC). Revenue month membership stays on the property timezone already computed by the backend. The client MUST NOT send browser TZ as a month override.
- **Why**: Board March totals (Sunset) are a property-calendar problem; "what time is it for me" is a profile problem. Mixing them recreates the original March bug.
- **Alternative considered**: Use profile TZ for revenue months. Rejected — a New York manager viewing a Paris property would drop `res-tz-1` from March.

### 3. Session tenant over simulated tenant

- **Choice**: Production path reads tenant from the authenticated session. `X-Simulated-Tenant` / `debugTenant` is opt-in debug only and MUST NOT default to `candidate`.
- **Why**: Hardcoded `candidate` maps everyone toward tenant-a in the challenge resolver and hides Ocean's empty `prop-001`.
- **Alternative considered**: Keep the header and teach the backend to honor it. Rejected for normal sessions; JWT tenant is the isolation boundary.

### 4. Red tests, then the smallest client fixes

- **Choice**: Land the harness and scenarios while they fail (hardcoded tenant, unscoped UI cache, browser TZ). Then change `RevenueSummary` / `SecureAPI` / display helpers until green.
- **Why**: Same loop as the backend change; the specs are the test list.

## Risks / Trade-offs

- **[Risk]** Heavily mocked `SecureAPI` misses a real header leak → **Mitigation**: Assert the exact `RequestInit` (URL + headers) the component issues, not only rendered text.
- **[Risk]** Profile timezone is UTC in challenge defaults, so display tests look like they pass on UTC data → **Mitigation**: Fixture a New York profile against a Paris browser in the display scenarios.
- **[Risk]** Vitest + Gherkin plugin drift → **Mitigation**: If the plugin fights Vite, keep the `.feature` files as the spec and implement steps as plain Vitest `describe`/`it` named after the scenarios.

## Migration Plan

1. Add Vitest config and `npm test` in `frontend/`.
2. Add features + failing steps (no product behavior change yet).
3. Fix client tenant default, cache keys, and timezone helpers until the suite is green.
4. Rollback: revert the frontend test deps and UI diffs; backend revenue behavior stays as-is.

No production data migration.
