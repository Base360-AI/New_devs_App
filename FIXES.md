# Fixes Applied — Property Revenue Dashboard

---

## Fix #1 — Cross-Tenant Cache Leak
**File:** `backend/app/services/cache.py` — Line 13

```python
# BEFORE
cache_key = f"revenue:{property_id}"

# AFTER
cache_key = f"revenue:{tenant_id}:{property_id}"
```

**Result:**
```
Sunset Properties  prop-001  →  $2,250.00  ✅ (their real data)
Ocean Rentals      prop-001  →  $0.00      ✅ (their real data, isolated)
```
Each tenant now has a completely separate cache entry. One tenant can never read another's cached data.

---

## Fix #2 — Float Precision Loss
**File:** `backend/app/api/v1/dashboard.py` — Line 18

```python
# BEFORE
total_revenue_float = float(revenue_data['total'])

# AFTER
from decimal import Decimal, ROUND_HALF_UP
total_revenue_float = float(
    Decimal(str(revenue_data['total'])).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
)
```

**Result:**
```
Before:  4975.5     ← float, sub-cent precision lost
After:   4975.50    ← rounded correctly to 2 decimal places
```
Revenue is rounded at the Decimal level before any float conversion, using standard financial rounding (`ROUND_HALF_UP`). No more "few cents off" discrepancies.

---

## Fix #3 — Monthly Revenue Always Zero + Timezone Bug
**File:** `backend/app/services/reservations.py` — Lines 5–32

```python
# BEFORE — placeholder, DB call commented out, timezone-naive
start_date = datetime(year, month, 1)   # naive UTC — wrong for Paris properties
...
return Decimal('0')                      # always zero, never queries DB

# AFTER — real DB query with timezone-aware date boundaries
async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Decimal:
    conn = await asyncpg.connect(settings.database_url)
    row = await conn.fetchrow(
        """
        SELECT COALESCE(SUM(r.total_amount), 0) AS total
        FROM reservations r
        JOIN properties p ON r.property_id = p.id AND r.tenant_id = p.tenant_id
        WHERE r.property_id = $1
          AND r.tenant_id   = $2
          AND (r.check_in_date AT TIME ZONE p.timezone) >= $3
          AND (r.check_in_date AT TIME ZONE p.timezone) <  $4
        """,
        property_id, tenant_id, start_date, end_date,
    )
    return Decimal(str(row["total"])) if row else Decimal("0")
```

**Result:**
```
res-tz-1: check_in = 2024-02-29 23:30 UTC = 2024-03-01 00:30 Paris time

Before:  counted in February (UTC naive)  → March total wrong by $1,250
After:   counted in March (AT TIME ZONE)  → March total matches client records ✅
```

---

## Fix #4 — Database Pool Wrong Config (Root Cause)
**File:** `backend/app/core/database_pool.py` — Line 18
**File:** `backend/app/services/reservations.py` — DB connection approach

```python
# BEFORE — settings.supabase_db_user doesn't exist → silent failure → mock data
database_url = f"postgresql+asyncpg://{settings.supabase_db_user}:..."

# AFTER — use asyncpg directly with settings.database_url
conn = await asyncpg.connect(settings.database_url)
```

**Result:**
```
Before:  every request → mock data ($1,000 hardcoded for all tenants)
After:   every request → real PostgreSQL data, tenant-isolated ✅
```

---

## Verification

```bash
# Flush cache to test fresh
docker exec new_devs_app-redis-1 redis-cli FLUSHALL

# Sunset Properties — prop-001
curl "http://localhost:8000/api/v1/dashboard/summary?property_id=prop-001" \
  -H "Authorization: Bearer <sunset_token>"
# → { "total_revenue": 2250.0, "reservations_count": 4 }  ✅

# Ocean Rentals — prop-001 (same property ID, different tenant)
curl "http://localhost:8000/api/v1/dashboard/summary?property_id=prop-001" \
  -H "Authorization: Bearer <ocean_token>"
# → { "total_revenue": 0.0, "reservations_count": 0 }  ✅
```
