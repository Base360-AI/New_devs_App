# PropertyFlow — Debug Challenge Solution

## Video Walkthrough
📹 **Loom:** https://www.loom.com/share/c9c9ba564fd44d2c9c1095c760134b40

The video explains how each bug was found, the root cause, and the fix.

## Summary

The app is a multi-tenant revenue dashboard. PropertyFlow manages rental properties for client companies (Sunset Properties, Ocean Rentals). Each client must see **only their own** data. The reported issues traced to the bugs below.

## Bugs Found & Fixed

| # | Bug | Root Cause | File | Fix |
|---|-----|-----------|------|-----|
| 1 | Cross-tenant cache leak | Redis cache key used only `property_id`, so tenants sharing an ID overwrote each other | `backend/app/services/cache.py` | Scoped the cache key by `tenant_id` |
| 2 | Revenue off by a few cents | Money cast from `Decimal` to binary `float`, losing cent precision | `backend/app/api/v1/dashboard.py` | Kept `Decimal`, rounded to 2 dp, returned as string |
| 3 | Wrong totals / mock data everywhere | DB pool built its URL from settings that don't exist and `get_session` was incorrectly `async`, so it always fell back to mock data | `backend/app/core/database_pool.py` | Connected to the real `database_url` with asyncpg and fixed `get_session` as a proper async context manager |
| 4 | March totals mismatch (timezone) | Monthly revenue bucketed by month in UTC, ignoring each property's timezone | `backend/app/services/reservations.py` | Bucketed by month in the property's own timezone using `AT TIME ZONE` |
| 5 | Dropdown showed all tenants' properties | Property list was hardcoded in the frontend; the backend endpoint it expected was missing | `backend/app/api/v1/dashboard.py`, `frontend/src/components/Dashboard.tsx` | Added a tenant-scoped `/properties` endpoint and loaded the dropdown from it |

## Notes

- Data was never altered to hide a bug — the duplicate property IDs and boundary reservation in `seed.sql` are valid real-world scenarios the code must handle correctly.
- Each fix is committed separately for clear review.

## Running

```bash
docker-compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000/docs

**Client logins**
- Sunset Properties — `sunset@propertyflow.com` / `client_a_2024`
- Ocean Rentals — `ocean@propertyflow.com` / `client_b_2024`
