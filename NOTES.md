# Investigation Notes
## Flex Property Revenue Dashboard

---

## Bug #4 — Database Pool Uses Non-Existent Config Attributes (Root Blocker)

**File:** `backend/app/core/database_pool.py`, **Line 18**

**Discovered:** While trying to reproduce Bug #1 live — both tenants showed identical `$1,000.00 / 3 bookings` which is hardcoded mock data, not real DB values.

**Error in logs:**
```
❌ Database pool initialization failed: 'Settings' object has no attribute 'supabase_db_user'
Database error for prop-005 (tenant: tenant-b): Database pool not available
```

**Root cause:**
```python
# BUGGY — builds URL from supabase_db_* attributes that don't exist in Settings
database_url = f"postgresql+asyncpg://{settings.supabase_db_user}:{settings.supabase_db_password}@{settings.supabase_db_host}:{settings.supabase_db_port}/{settings.supabase_db_name}"
```

The `Settings` class (config.py) has `database_url: str = "postgresql://postgres:postgres@db:5432/propertyflow"` — a single connection string. The pool was written expecting Supabase-style split fields (`host`, `port`, `user`, `password`) that were never defined.

**Impact:**
- Every call to `calculate_total_revenue()` fails silently
- Falls back to hardcoded mock data in `reservations.py` (same values for all tenants)
- **Masks Bug #1** — mock data is identical across tenants so the cache leak is invisible
- **Masks Bug #2** — mock amounts are clean integers, no floating point edge cases
- **The system appears to work but is never touching the real database**

**First fix attempt — `database_pool.py`:**
```python
# FIXED URL building
database_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
```
This fixed the attribute error but exposed a second issue: `greenlet` library is missing from `requirements.txt`. SQLAlchemy async requires `sqlalchemy[asyncio]` (which pulls in greenlet), but only bare `sqlalchemy>=2.0.0` is listed. Fixing `requirements.txt` would require a full Docker rebuild.

**Final fix — bypassed SQLAlchemy entirely, used `asyncpg` directly in `reservations.py`:**
`asyncpg` is already installed in the container. Rewrote `calculate_total_revenue` to open a direct asyncpg connection using `settings.database_url` — no SQLAlchemy, no greenlet, no rebuild needed.

**Result confirmed via curl:**
```
tenant-a prop-001 → $2,250.00 / 4 reservations  (real DB data ✅)
tenant-b prop-001 → $2,250.00 / 4 reservations  (WRONG — cache leak bug visible ✅)
```
Ocean Rentals has zero reservations for prop-001. The fact that they see $2,250 is Bug #1 in action.

---

## Bug #1 — Cross-Tenant Cache Leak (Privacy)

**File:** `backend/app/services/cache.py`, **Line 13**

**Visible after:** Fixing Bug #4 so real DB data flows.

```python
# BUGGY
cache_key = f"revenue:{property_id}"

# FIXED
cache_key = f"revenue:{tenant_id}:{property_id}"
```

Both tenants share `prop-001` (valid — composite PK in schema). Without `tenant_id` in the key, whichever tenant requests first wins and the other gets their data from cache.

- tenant-a `prop-001` real revenue: **$2,250.000** (4 reservations)
- tenant-b `prop-001` real revenue: **$0.00** (no reservations)

---

## Bug #2 — Float Precision on Revenue Totals

**File:** `backend/app/api/v1/dashboard.py`, **Line 18**

```python
# BUGGY
total_revenue_float = float(revenue_data['total'])

# FIXED
from decimal import Decimal, ROUND_HALF_UP
total_revenue_float = float(
    Decimal(str(revenue_data['total'])).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
)
```

DB stores `NUMERIC(10,3)`. Seed data has intentional 3-decimal amounts (`333.333`) that expose IEEE 754 float imprecision. The frontend also has a hidden `Precision Mismatch Detected` warning in `RevenueSummary.tsx` as a hint.

---

## Bug #3 — Monthly Revenue Always Returns Zero

**File:** `backend/app/services/reservations.py`, **Line 32**

```python
return Decimal('0')  # Placeholder — DB query is written but commented out, never runs
```

Also contains a timezone bug: `datetime(year, month, 1)` is timezone-naive. Properties in `Europe/Paris` have reservations that cross midnight UTC/local boundaries — e.g., `res-tz-1` checks in at `2024-02-29 23:30 UTC` = `2024-03-01 00:30 Paris`, so it belongs in March by the client's reckoning but falls in February in a UTC query.

---

## Order of Fixes

1. **Bug #4** — `database_pool.py` — fix DB connection so real data flows ✅ APPLIED
2. **Bug #1** — `cache.py` — add `tenant_id` to cache key
3. **Bug #2** — `dashboard.py` — fix float precision
4. **Bug #3** — `reservations.py` — implement monthly revenue with timezone-aware dates
5. *(Bonus)* — `Dashboard.tsx` — fetch properties from API instead of hardcoding all 5

---

## Key Files

| File | Role |
|------|------|
| `backend/app/core/database_pool.py` | SQLAlchemy async pool — was using wrong config attributes |
| `backend/app/services/cache.py` | Redis cache for revenue — missing tenant_id in key |
| `backend/app/services/reservations.py` | Revenue calculation — monthly function is a placeholder |
| `backend/app/api/v1/dashboard.py` | Dashboard endpoint — float conversion loses precision |
| `frontend/src/components/Dashboard.tsx` | Hardcodes all 5 properties for all tenants |
| `database/seed.sql` | Both tenants share prop-001 (intentional to expose cache bug) |
