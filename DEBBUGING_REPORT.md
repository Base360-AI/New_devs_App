# 🐛 Property Revenue Dashboard - Debugging Report

## Project Overview

**Property Revenue Dashboard** is a multi-tenant system that manages revenue for property management companies. It has 2 main clients:
- **Sunset Properties** (tenant-a) - Email: `sunset@propertyflow.com`
- **Ocean Rentals** (tenant-b) - Email: `ocean@propertyflow.com`

Password: `client_a_2024` / `client_b_2024`

**Tech Stack:** Python FastAPI + Supabase + PostgreSQL + Redis (backend) | React/TypeScript (frontend) | Docker Compose

---

## 6 Bugs Found & Fixed

### Bug 1 🔴 - Cache Missing Tenant Isolation (Privacy Issue)

**Severity:** Critical - Privacy violation

**File:** `backend/app/services/cache.py` (line 13)

**Root Cause:**
```python
# ❌ BEFORE FIX
cache_key = f"revenue:{property_id}"
```
The cache key only included `property_id` without `tenant_id`. When Redis had cached data for `prop-001` from tenant-a, if tenant-b requested `prop-001`, they received tenant-a's cached data → **Client B sees Client A's revenue data**.

**Fix:**
```python
# ✅ AFTER FIX
cache_key = f"revenue:{tenant_id}:{property_id}"
```
Added `tenant_id` to the cache key so each tenant has their own isolated cache.

---

### Bug 2 🟡 - Floating Point Precision Loss (Revenue off by cents)

**Severity:** Medium - Affects financial report accuracy

**Files:** `backend/app/api/v1/dashboard.py` (line 18) + `frontend/src/components/RevenueSummary.tsx`

**Root Cause:**
```python
# ❌ BEFORE FIX
total_revenue_float = float(revenue_data['total'])
```
Revenue from the database is `Decimal` → converted to string → then `float()`. The IEEE 754 float type cannot accurately represent all decimal numbers (e.g., `0.1 + 0.2 = 0.30000000000000004`), causing the "few cents off" issue.

**Fix:**
```python
# ✅ AFTER FIX (backend)
total_revenue_str = revenue_data['total']  # Keep as string
```
```typescript
// ✅ AFTER FIX (frontend)
interface RevenueData {
  total_revenue: string;  // was 'number'
}
const displayTotal = Math.round(parseFloat(data.total_revenue) * 100) / 100;
```
Backend returns a string instead of float. Frontend uses `parseFloat()` when displaying.

---

### Bug 3 🟢 - Shared Mock Data Across Tenants

**Severity:** Low - Only affects when DB is offline

**File:** `backend/app/services/reservations.py` (lines 97-112)

**Root Cause:**
```python
# ❌ BEFORE FIX
mock_data = {
    'prop-001': {'total': '1000.00', 'count': 3},
    # ... Shared across ALL tenants!
}
```
When the database was unavailable, the mock data fallback was a single global dict → both tenants saw identical revenue figures.

**Fix:**
```python
# ✅ AFTER FIX
mock_data = {
    'tenant-a': {
        'prop-001': {'total': '1000.00', 'count': 3},
        # ... Separate data for Sunset
    },
    'tenant-b': {
        'prop-001': {'total': '2500.00', 'count': 5},
        # ... Separate data for Ocean
    }
}
```
Split mock data per tenant with different revenue figures.

---

### Bug 4 🟠 - Monthly Revenue Function Missing Tenant Parameter

**Severity:** High - Causes incorrect monthly reports (Client A's March issue)

**File:** `backend/app/services/reservations.py` (line 16)

**Root Cause:**
```python
# ❌ BEFORE FIX
async def calculate_monthly_revenue(property_id: str, month: int, year: int, db_session=None) -> Decimal:
```
The function signature was missing `tenant_id`. The SQL query inside referenced `tenant_id = $2` but the parameter was never passed in. This means **Client A's March revenue numbers were wrong** because the query couldn't filter by tenant.

**Fix:**
```python
# ✅ AFTER FIX
async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int, db_session=None) -> Decimal:
```
Added `tenant_id` parameter to the function signature so it can properly filter revenue by tenant. Also added `tenant_id` to the debug print.

---

### Bug 5 ⚪ - DB Pool Not Singleton / Session Not Awaited

**Severity:** Medium - Performance + potential runtime crashes

**File:** `backend/app/services/reservations.py` (lines 43-54)

**Root Cause (2 issues):**

```python
# ❌ BEFORE FIX
from app.core.database_pool import DatabasePool

db_pool = DatabasePool()       # Issue 1: New pool created on EVERY request
await db_pool.initialize()

if db_pool.session_factory:
    async with db_pool.get_session() as session:  # Issue 2: get_session() returns a coroutine, not awaited!
```

1. **Issue 1:** `DatabasePool()` was instantiated on every request → wastes resources creating new connection pools
2. **Issue 2:** `db_pool.get_session()` returns a **coroutine** but was used directly in `async with` without `await` → would crash at runtime

**Fix:**
```python
# ✅ AFTER FIX
# Singleton pattern
_db_pool_instance = None

async def get_db_pool():
    global _db_pool_instance
    if _db_pool_instance is None:
        from app.core.database_pool import DatabasePool
        _db_pool_instance = DatabasePool()
        await _db_pool_instance.initialize()
    return _db_pool_instance

# In calculate_total_revenue:
db_pool = await get_db_pool()                   # Uses singleton
if db_pool.session_factory:
    async with await db_pool.get_session() as session:  # Properly awaited
```

---

### Bug 6 📦 - sqlalchemy Import at Top Level Would Crash Module

**Severity:** Medium - Module would fail to load if sqlalchemy is missing

**File:** `backend/app/services/reservations.py` (line 50)

**Root Cause:**
```python
# ❌ BEFORE FIX
from sqlalchemy import text  # At top of file → crash on import if library missing
```
If `sqlalchemy` wasn't installed, the entire module would fail to load, preventing the mock data fallback from working.

**Fix:**
```python
# ✅ AFTER FIX
# Inside try block of calculate_total_revenue():
try:
    from sqlalchemy import text  # Graceful: if missing, caught by except → mock data fallback
```
Moved import inside the `try` block so if the library is missing, it falls back to mock data instead of crashing.

---

## Files Modified

| File | Bug | Change |
|------|-----|--------|
| `backend/app/services/cache.py` | Bug 1 | Added `tenant_id` to cache key |
| `backend/app/api/v1/dashboard.py` | Bug 2 | Return string instead of float |
| `frontend/src/components/RevenueSummary.tsx` | Bug 2 | `parseFloat()`, interface `total_revenue` changed to `string` |
| `backend/app/services/reservations.py` | Bug 3 | Split mock data by tenant |
| `backend/app/services/reservations.py` | Bug 4 | Added `tenant_id` param to `calculate_monthly_revenue()` |
| `backend/app/services/reservations.py` | Bug 5 | Singleton pool, `await get_session()` |
| `backend/app/services/reservations.py` | Bug 6 | `sqlalchemy` import moved into try/except |

---

## How to Run

```bash
docker-compose up --build
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000/docs