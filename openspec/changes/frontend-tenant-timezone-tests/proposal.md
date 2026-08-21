## Why

Backend revenue isolation and property-timezone month windows are covered by BDD, but the dashboard UI has no frontend tests. `RevenueSummary` still defaults `prop-001` and a `candidate` simulated tenant, client caches can mix tenants, and date display can use the browser zone instead of the signed-in user's profile timezone.

## What Changes

- Add frontend tests (BDD-style where practical) for the same isolation and timezone contracts the backend now enforces.
- Assert revenue fetches use the authenticated user's tenant, not a hardcoded simulated tenant.
- Assert client-side caches and request keys include tenant identity so a refresh cannot show another company's totals.
- Assert user-facing clocks and date labels use the profile timezone; monthly revenue queries must not substitute the browser timezone for the property timezone.
- Add a frontend test runner (none exists today) so these scenarios can fail first, then drive UI fixes.

## Capabilities

### New Capabilities

- `frontend-tenant-isolation`: Dashboard and API client keep tenant A and tenant B data apart in requests, headers, and browser caches.
- `user-timezone`: User-visible times use the profile timezone; revenue month windows stay on the property timezone and are not rewritten to the browser zone.

### Modified Capabilities

- None. There are no existing main specs under `openspec/specs/`.

## Impact

- **Frontend**: `RevenueSummary`, `SecureAPI.getDashboardSummary`, `secureCache` / `tenantIsolatedStorage`, profile timezone field.
- **Tests**: new frontend test harness (Vitest + Testing Library, Gherkin via cucumber/vitest-bdd or equivalent).
- **Backend**: no API change required unless tests prove `X-Simulated-Tenant` must be ignored in favor of JWT tenant (already true).
- **Not in scope**: rebuilding the dashboard, physical DB isolation, or changing board totals away from property timezone.
