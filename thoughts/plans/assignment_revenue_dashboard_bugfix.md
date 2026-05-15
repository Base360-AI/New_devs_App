# Assignment Revenue Dashboard Bugfix Implementation Plan

## Overview

Implement a focused, minimal fix for the Property Revenue Dashboard assignment. The plan addresses the known revenue accuracy, tenant isolation, caching, timezone, and precision bugs while leaving room to fix any additional correctness, privacy, security, or reliability bugs discovered during execution.

## Current State Analysis

The assignment path is small and should stay small. The frontend dashboard calls one backend summary endpoint, which delegates to a Redis-backed revenue service. The existing implementation has several high-risk defects in that path.

The backend dashboard endpoint accepts only `property_id`, derives a tenant from auth, calls the cache service, converts the total to `float`, and returns a minimal response. The endpoint has no `month` or `year` support.

The cache service receives `tenant_id`, but its key uses only `property_id`. The seed data intentionally reuses `prop-001` for both tenants, making this a direct cross-tenant cache collision risk.

The revenue service has a placeholder `calculate_monthly_revenue()` and a live `calculate_total_revenue()` that sums all reservations for a tenant/property. It also builds a database pool from missing Supabase-specific settings instead of the Docker `DATABASE_URL`, which likely triggers fallback mock data.

The frontend hardcodes all properties for both tenants, defaults to `prop-001`, and sends only `property_id`. The UI rounds JavaScript numbers for display and does not expose the report period or property-local timezone behavior.

## Desired End State

The dashboard returns tenant-scoped, month-specific, property-timezone-aware March 2024 revenue totals for the authenticated client. The cache cannot leak between tenants or report periods. Money values cross the API as decimal strings. The frontend fetches tenant-scoped properties from the backend, defaults to March 2024, and displays a concise property-local reporting label.

Execution should also inspect nearby assignment-path code and fix any additional correctness, privacy, security, or reliability bugs discovered, as long as they do not require a major refactor. If a major refactor appears necessary, stop and ask for approval.

### Key Discoveries

- `backend/app/api/v1/dashboard.py:8-24` defines the only assignment dashboard summary endpoint and currently returns `total_revenue` as a float.
- `backend/app/services/cache.py:9-29` caches revenue by `property_id` only, omitting `tenant_id`, `month`, and `year`.
- `backend/app/services/reservations.py:5-32` has a placeholder monthly revenue helper that always returns `Decimal('0')`.
- `backend/app/services/reservations.py:51-59` sums all-time reservation revenue, not March revenue.
- `backend/app/core/database_pool.py:18-21` builds a database URL from missing Supabase-specific settings instead of `settings.database_url`.
- `database/seed.sql:8-9` intentionally duplicates `prop-001` across tenants, which exposes tenant-unsafe cache keys and UI logic.
- `database/seed.sql:19` puts a Paris reservation at `2024-02-29 23:30:00+00`, which is March 1 in `Europe/Paris`.
- `database/seed.sql:24-26` uses sub-cent values that sum exactly to `1000.000`, which exposes decimal precision issues.
- `frontend/src/components/Dashboard.tsx:4-10` hardcodes all tenant properties in the selector.
- `frontend/src/components/RevenueSummary.tsx:64` rounds money with JavaScript number arithmetic.
- `frontend/src/lib/secureApi.ts:1455-1468` only sends `property_id` to the dashboard summary endpoint.
- `backend/pyproject.toml:42-44` configures pytest, but pytest is not listed in dependencies.

## What We're NOT Doing

- Rebuilding the broader application or replacing the auth system.
- Refactoring unrelated modules such as cleaning, profile, departments, or legacy Supabase-backed screens.
- Building a full finance reporting module beyond the assignment dashboard path.
- Adding a complex date picker or multi-month analytics UI.
- Removing fallback mock data entirely; fallback stays, but must be tenant-aware and clearly flagged.
- Adding accessibility work unless it fixes a functional bug.
- Adding production-hardening changes unless they affect local assignment behavior or verification.

## Implementation Approach

Use a minimal assignment-path fix. Start with backend data correctness and tenant isolation, then wire the frontend to the corrected API. Add targeted backend tests because the bugs are data and API behavior bugs. Finish with manual verification steps and a written walkthrough that supports the final presentation.

If execution finds additional bugs, apply this rule:

- Fix immediately if the bug affects correctness, privacy, security, reliability, or assignment verification and can be fixed with a small localized change.
- Document and ask before proceeding if the bug requires a broad refactor, schema redesign, or changes outside the assignment path.

## Phase 1: Backend Data Access And Domain Logic

### Overview

Make the backend capable of reading the Docker database, listing tenant-scoped properties, and calculating month-specific revenue using property-local time.

### Changes Required

#### 1. Database Pool Configuration

**File**: `backend/app/core/database_pool.py`

**Changes**:
- Use the existing global `db_pool` instead of creating a new pool for every revenue request.
- Build the async SQLAlchemy URL from `settings.database_url`.
- Convert `postgresql://` to `postgresql+asyncpg://` when needed.
- Keep pool settings from `settings.database_pool_size`, `settings.database_max_overflow`, and `settings.database_pool_recycle`.

```python
def _async_database_url() -> str:
    url = settings.database_url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url
```

**Rationale**:
`docker-compose.yml:9` provides `DATABASE_URL`, but `database_pool.py:18` currently expects missing Supabase-specific settings. Fixing this lets the app use the seeded Postgres data instead of falling into fallback mode.

#### 2. Property And Revenue Service Methods

**File**: `backend/app/services/reservations.py`

**Changes**:
- Replace the placeholder monthly function with real tenant-scoped logic.
- Add `get_tenant_properties(tenant_id)` returning `id`, `name`, and `timezone` from `properties`.
- Add `get_property_for_tenant(property_id, tenant_id)` to validate ownership and retrieve timezone.
- Add `calculate_monthly_revenue(property_id, tenant_id, month, year)` returning a dict with `property_id`, `tenant_id`, `property_name`, `property_timezone`, `reporting_period`, `total`, `currency`, `count`, and `is_fallback`.
- Convert property-local month boundaries to UTC before querying `check_in_date`.
- Use `Decimal` and quantize final display/API totals to two decimals using an explicit rounding mode.
- Keep fallback data, but key it by tenant and property.
- Include a clear fallback marker, such as `is_fallback: True`, and log fallback usage.

```python
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

def month_bounds_utc(year: int, month: int, property_timezone: str):
    local_tz = ZoneInfo(property_timezone)
    local_start = datetime(year, month, 1, tzinfo=local_tz)
    if month == 12:
        local_end = datetime(year + 1, 1, 1, tzinfo=local_tz)
    else:
        local_end = datetime(year, month + 1, 1, tzinfo=local_tz)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)
```

**Rationale**:
The assignment reports March mismatches and properties in different time zones. The Paris `2024-02-29 23:30:00+00` reservation belongs to March locally, so UTC month filtering would be wrong.

#### 3. Tenant-Aware Fallback Fixtures

**File**: `backend/app/services/reservations.py`

**Changes**:
- Replace property-only fallback data with tenant/property fallback data.
- Include only properties that belong to the tenant.
- Return `0.00` or a 404-style error for tenant/property mismatches rather than another tenant's fallback data.
- Include `is_fallback: True` and a `fallback_reason` when fallback is used.

```python
FALLBACK_PROPERTIES = {
    "tenant-a": [
        {"id": "prop-001", "name": "Beach House Alpha", "timezone": "Europe/Paris"},
        {"id": "prop-002", "name": "City Apartment Downtown", "timezone": "Europe/Paris"},
        {"id": "prop-003", "name": "Country Villa Estate", "timezone": "Europe/Paris"},
    ],
    "tenant-b": [
        {"id": "prop-001", "name": "Mountain Lodge Beta", "timezone": "America/New_York"},
        {"id": "prop-004", "name": "Lakeside Cottage", "timezone": "America/New_York"},
        {"id": "prop-005", "name": "Urban Loft Modern", "timezone": "America/New_York"},
    ],
}
```

**Rationale**:
Mocked data may be intentional for the test, but tenant-insensitive fallback can create the same privacy bug as the cache.

### Success Criteria

#### Automated Verification
- [x] Backend imports succeed: `python3 -m compileall app` from `backend`.
- [x] New service tests pass once added in Phase 4: `uv run python -m pytest` from `backend`.

#### Manual Verification
- [ ] Backend starts through Docker without revenue requests falling into fallback because of missing Supabase DB settings.
- [ ] If the database is intentionally unavailable, fallback responses are tenant-aware and include fallback metadata.

---

## Phase 2: Backend API And Cache Safety

### Overview

Expose tenant-scoped properties, update the dashboard summary API for month/year, preserve decimal strings, and make Redis cache keys tenant-safe.

### Changes Required

#### 1. Dashboard Properties Endpoint

**File**: `backend/app/api/v1/dashboard.py`

**Changes**:
- Add `GET /dashboard/properties`.
- Authenticate with `get_current_user`.
- Require a valid `tenant_id`; do not silently fall back to `default_tenant`.
- Return only properties belonging to the authenticated tenant.
- Include property timezone because the UI needs the local-period label.

```python
@router.get("/dashboard/properties")
async def get_dashboard_properties(current_user = Depends(get_current_user)):
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Missing tenant context")
    return {"properties": await get_tenant_properties(tenant_id)}
```

#### 2. Dashboard Summary Endpoint

**File**: `backend/app/api/v1/dashboard.py`

**Changes**:
- Add `month: int = 3` and `year: int = 2024` query parameters.
- Validate month is `1...12` and year is reasonable for assignment data.
- Require valid tenant context.
- Call `get_revenue_summary(property_id, tenant_id, month, year)`.
- Return `total_revenue` as a decimal string, not a float.
- Return metadata: `property_name`, `property_timezone`, `reporting_period`, `is_fallback`.

```python
return {
    "property_id": revenue_data["property_id"],
    "property_name": revenue_data["property_name"],
    "property_timezone": revenue_data["property_timezone"],
    "reporting_period": {"month": month, "year": year, "label": "March 2024"},
    "total_revenue": revenue_data["total"],
    "currency": revenue_data["currency"],
    "reservations_count": revenue_data["count"],
    "is_fallback": revenue_data.get("is_fallback", False),
}
```

#### 3. Revenue Cache Key

**File**: `backend/app/services/cache.py`

**Changes**:
- Change signature to `get_revenue_summary(property_id, tenant_id, month, year)`.
- Use a cache key that includes tenant, property, month, and year.
- Optionally validate cached payload tenant matches before returning.
- Cache only JSON-serializable decimal-string responses.

```python
cache_key = f"revenue:{tenant_id}:{property_id}:{year}:{month:02d}"
```

**Rationale**:
The current `revenue:{property_id}` key leaks when `prop-001` exists under both tenants.

### Success Criteria

#### Automated Verification
- [x] New tests confirm cache keys differ for `tenant-a/prop-001` and `tenant-b/prop-001`.
- [x] New tests confirm summary responses use string totals.
- [ ] New tests confirm invalid month returns a 422 or 400 response.

#### Manual Verification
- [ ] `GET /api/v1/dashboard/properties` returns only Sunset properties when using Sunset token.
- [ ] `GET /api/v1/dashboard/properties` returns only Ocean properties when using Ocean token.
- [ ] `GET /api/v1/dashboard/summary?property_id=prop-001&month=3&year=2024` returns different tenant-owned property metadata for Sunset vs Ocean.
- [ ] Repeated refreshes do not cross-pollinate data between clients.

---

## Phase 3: Frontend Dashboard Integration

### Overview

Update the dashboard to use the backend as the source of truth for tenant-scoped properties and report metadata.

### Changes Required

#### 1. SecureAPI Dashboard Methods

**File**: `frontend/src/lib/secureApi.ts`

**Changes**:
- Add `getDashboardProperties()` calling `/api/v1/dashboard/properties`.
- Update `getDashboardSummary()` to accept `{ month, year }`.
- Remove `simulatedTenant` from dashboard summary usage. It is not honored by the backend and is misleading.
- Keep timestamp optional only if needed for cache busting, but do not rely on it for correctness.

```ts
async getDashboardSummary(propertyId: string, options: { month: number; year: number }) {
  const queryParams = new URLSearchParams({
    property_id: propertyId,
    month: String(options.month),
    year: String(options.year),
  });
  return this.request<any>(`/api/v1/dashboard/summary?${queryParams}`);
}
```

#### 2. Dashboard Property Loading

**File**: `frontend/src/components/Dashboard.tsx`

**Changes**:
- Remove the global `PROPERTIES` constant.
- Fetch tenant-scoped properties on mount with `SecureAPI.getDashboardProperties()`.
- Store selected property from the first returned property.
- Pass `month={3}` and `year={2024}` to `RevenueSummary`.
- Show a simple loading/error state for property loading. This is not broad UI polish; it is needed for a data-driven selector.
- Keep UI design close to the current screen.

```tsx
const REPORT_MONTH = 3;
const REPORT_YEAR = 2024;
```

#### 3. Revenue Summary Display

**File**: `frontend/src/components/RevenueSummary.tsx`

**Changes**:
- Change `total_revenue` type from `number` to `string`.
- Accept `month` and `year` props.
- Remove `debugTenant` and `activeTenant` from normal dashboard flow.
- Format decimal strings safely for display.
- Display `March 2024, property local time` using response metadata.
- Show fallback marker only if `is_fallback` is true, using understated copy such as `Using fallback data`.

```ts
interface RevenueData {
  property_id: string;
  property_name: string;
  property_timezone: string;
  total_revenue: string;
  currency: string;
  reservations_count: number;
  is_fallback?: boolean;
}
```

### Success Criteria

#### Automated Verification
- [x] Frontend builds: `npm run build` from `frontend`.
- [x] Frontend lint is run if practical: `npm run lint` from `frontend`.

#### Manual Verification
- [ ] Sunset login shows only Sunset properties: Beach House Alpha, City Apartment Downtown, Country Villa Estate.
- [ ] Ocean login shows only Ocean properties: Mountain Lodge Beta, Lakeside Cottage, Urban Loft Modern.
- [ ] Dashboard defaults to March 2024.
- [ ] Revenue total renders from a decimal string with two fraction digits.
- [ ] UI shows the reporting-period label as property-local time.
- [ ] Fallback marker appears only when backend reports fallback data.

---

## Phase 4: Tests, Bug Sweep, And Verification Artifacts

### Overview

Add targeted tests for the highest-risk bugs and perform a final sweep for additional assignment-path defects.

### Changes Required

#### 1. Add Backend Test Dependency

**File**: `backend/pyproject.toml`

**Changes**:
- Add `pytest` to `dependency-groups.dev`.
- Add `pytest-asyncio` if async service tests need it.
- Keep this as a dev dependency only.

```toml
[dependency-groups]
dev = [
    "pre-commit>=4.3.0",
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
]
```

#### 2. Add Targeted Backend Tests

**Files**:
- `backend/tests/test_dashboard_revenue.py`
- `backend/tests/test_revenue_cache.py`

**Changes**:
- Test cache key construction or behavior separates tenant/property/month/year.
- Test monthly boundary helper converts Paris March 2024 start to `2024-02-29T23:00:00Z` or equivalent UTC datetime.
- Test decimal formatting returns strings, not floats.
- Test tenant-aware fallback does not return Tenant A property metadata for Tenant B.
- Test invalid month/year validation at the API layer if practical.

#### 3. Assignment-Path Bug Sweep

**Files**:
- `backend/app/api/v1/dashboard.py`
- `backend/app/services/cache.py`
- `backend/app/services/reservations.py`
- `backend/app/core/database_pool.py`
- `frontend/src/components/Dashboard.tsx`
- `frontend/src/components/RevenueSummary.tsx`
- `frontend/src/lib/secureApi.ts`
- `database/schema.sql`
- `database/seed.sql`

**Changes**:
- Re-read the touched code after implementation.
- Search for remaining `float`, `Math.round`, tenant-insensitive cache keys, hardcoded cross-tenant properties, and ignored `tenant_id` in the assignment path.
- Fix any small bug found under the agreed rule.
- Stop and ask before any large refactor.

#### 4. Written Walkthrough

**File**: `thoughts/walkthroughs/assignment_revenue_dashboard_debugging.md`

**Changes**:
- Create a concise walkthrough the user can read before recording.
- Include each bug's symptom, root cause, fix, and verification.
- Include advice for a 5-10 minute demo.

Recommended sections:

- What I investigated
- Bug 1: Tenant-unsafe cache key
- Bug 2: All-tenant property selector
- Bug 3: All-time totals instead of March totals
- Bug 4: Timezone month boundary handling
- Bug 5: Float/JavaScript money precision
- Bug 6: Docker DB config/fallback behavior
- Extra bugs found during implementation, if any
- Verification checklist
- Presentation script

### Success Criteria

#### Automated Verification
- [x] Backend tests pass: `uv run python -m pytest` from `backend`.
- [x] Backend compiles: `python3 -m compileall app` from `backend`.
- [x] Frontend builds: `npm run build` from `frontend`.
- [x] Frontend lint is run if practical: `npm run lint` from `frontend`.

Lint note: `npm run lint` was executed and failed on existing repository-wide ESLint issues, primarily `no-explicit-any` and unused variables across legacy files. A targeted lint run against the touched frontend files still reports pre-existing `secureApi.ts` issues outside the dashboard changes; `Dashboard.tsx` and `RevenueSummary.tsx` did not add new lint errors.

#### Manual Verification
- [ ] Start the stack: `docker compose up --build`.
- [ ] Log in as Sunset Properties with `sunset@propertyflow.com` / `client_a_2024`.
- [ ] Confirm only Sunset properties appear.
- [ ] Confirm March 2024 totals include the Paris boundary reservation for `prop-001`.
- [ ] Log in as Ocean Rentals with `ocean@propertyflow.com` / `client_b_2024`.
- [ ] Confirm only Ocean properties appear.
- [ ] Refresh both dashboards repeatedly and verify no cross-tenant revenue appears.
- [ ] Query `/api/v1/dashboard/properties` directly with each token and verify tenant-scoped responses.
- [ ] Query `/api/v1/dashboard/summary` directly with each token, `property_id=prop-001`, `month=3`, and `year=2024` and verify different tenant-specific property metadata.
- [ ] Confirm totals are decimal strings in raw API responses.
- [ ] Confirm fallback data, if triggered, is tenant-aware and clearly marked.

---

## Testing Strategy

### Unit Tests

- Test month boundary conversion for `Europe/Paris` and `America/New_York`.
- Test decimal formatting and rounding from `Decimal` to API string.
- Test fallback property lookup respects `tenant_id`.
- Test revenue cache key includes `tenant_id`, `property_id`, `year`, and `month`.

### Integration Tests

- Test dashboard summary endpoint with mocked auth user for `tenant-a` and `tenant-b`.
- Test dashboard properties endpoint returns tenant-scoped lists only.
- Test invalid property access returns a safe empty/404/403 response rather than another tenant's data.

### Manual Testing Steps

1. Start the stack with `docker compose up --build`.
2. Login as Sunset Properties.
3. Verify property selector contains only Sunset properties.
4. Verify `prop-001` March 2024 total includes the Paris boundary reservation.
5. Login as Ocean Rentals in a clean session or after logout.
6. Verify property selector contains only Ocean properties.
7. Refresh repeatedly and verify totals never show Sunset property names or totals.
8. Use backend docs or curl to call properties and summary endpoints with both tokens.
9. Confirm raw summary response uses string totals and includes period/timezone metadata.
10. Review the walkthrough and confirm it matches observed behavior.

## Performance Considerations

- The revenue query should filter by tenant, property, and bounded check-in dates, keeping the result set small.
- Redis cache remains useful but must use tenant-safe keys.
- Avoid creating a new database engine per request; use the global pool.
- Frontend property loading happens once per dashboard mount and should be lightweight.

## Migration Notes

No persistent schema migration is required. Existing schema already stores tenant-scoped properties, property timezones, reservation timestamps, and numeric amounts.

If changes to seed data are needed during execution, only adjust data that is proven inconsistent with the assignment or that blocks reliable verification.

## References

- Original ticket: `thoughts/tickets/bug_assignment_debugging.md`
- Related research: `thoughts/research/2026-05-15_assignment_debugging.md`
- Assignment: `ASSIGNMENT.md`
- Dashboard endpoint: `backend/app/api/v1/dashboard.py:8-24`
- Revenue cache: `backend/app/services/cache.py:9-29`
- Revenue service: `backend/app/services/reservations.py:5-109`
- Database pool: `backend/app/core/database_pool.py:9-60`
- Docker database config: `docker-compose.yml:8-11`
- Frontend dashboard: `frontend/src/components/Dashboard.tsx:4-57`
- Frontend revenue card: `frontend/src/components/RevenueSummary.tsx:1-119`
- SecureAPI dashboard method: `frontend/src/lib/secureApi.ts:1451-1469`
- Schema: `database/schema.sql:12-31`
- Seed fixtures: `database/seed.sql:8-47`
