# Changelog

## Bug Fixes — branch `fix-bug`

---

### Bug 1 — Cross-tenant data leakage via Redis cache (Privacy — Critical)

**File:** `backend/app/services/cache.py`

**Root cause:** The Redis cache key was `revenue:{property_id}` only.
Because `prop-001` is assigned to *both* `tenant-a` and `tenant-b` in the seed data,
the first tenant to load Beach House Alpha would populate `revenue:prop-001` in Redis.
Any subsequent request for `prop-001` — regardless of which tenant made it — would
receive the cached result of the *other* tenant, leaking private financial data.

**Fix:** Changed the cache key to `revenue:{tenant_id}:{property_id}` so each tenant
maintains its own isolated cache entry.

---

### Bug 2 — Floating-point precision error in revenue totals (Finance — High)

**File:** `backend/app/api/v1/dashboard.py`

**Root cause:** The total revenue stored in the DB uses `NUMERIC(10,3)` (3 decimal
places). The service returned it as a Python `str` (e.g. `"999.999"`). The API
converted it directly with `float()` before returning to the frontend. IEEE 754 float
arithmetic can introduce sub-cent rounding errors (e.g. `333.333 + 333.333 + 333.334`
becomes `999.9999999999999` in float), causing the finance team to see amounts that
are off by a few cents.

**Fix:** The total is now rounded to 2 decimal places using `Decimal.quantize()`
with `ROUND_HALF_UP` *before* the `float()` conversion, ensuring the returned value
is always a correctly-rounded two-decimal-place amount.

---

### Bug 3 — Monthly revenue ignores property timezone (Accuracy — High)

**File:** `backend/app/services/reservations.py` — `calculate_monthly_revenue()`

**Root cause:** The function built month-boundary datetimes with `datetime(year, month, 1)`,
which produces a **naive** (timezone-unaware) datetime. The DB stores `check_in_date`
as `TIMESTAMP WITH TIME ZONE` (UTC). For properties in `Europe/Paris` (UTC+1), a
check-in at `2024-02-29 23:30 UTC` is actually `2024-03-01 00:30` local time — the
guest arrives in March. The naive UTC boundary `2024-03-01 00:00` placed this booking
in February, so it was excluded from the March revenue report.

**Fix:** Added a `property_timezone` parameter. Boundaries are now constructed in the
property's local timezone using `ZoneInfo`, then converted to UTC-aware datetimes for
the DB query.

---

### Bug 4 — Dashboard property list hardcoded, exposing other tenants' properties (Privacy — Critical)

*Previously labelled Bug 5.*

**Files:** `frontend/src/components/Dashboard.tsx`, `frontend/src/lib/secureApi.ts`,
`backend/app/api/v1/dashboard.py`

**Root cause:** The frontend `Dashboard.tsx` contained a static `PROPERTIES` array
listing all five properties across *both* tenants. Every logged-in user saw
`Lakeside Cottage` and `Urban Loft Modern` (tenant-b) alongside tenant-a's properties,
and vice-versa.

**Fix:**
- Added `GET /api/v1/dashboard/properties` backend endpoint that queries the `properties`
  table filtered by the authenticated user's `tenant_id`. Falls back to per-tenant mock
  data when the DB is unavailable.
- Added `SecureAPI.getDashboardProperties()` method in `secureApi.ts`.
- Rewrote `Dashboard.tsx` to fetch the property list from the API on mount; the
  dropdown is now populated dynamically and only shows properties belonging to the
  current tenant.
