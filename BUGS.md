# Bugs Found — Property Revenue Dashboard

---

## Bug #1 — Cross-Tenant Cache Leak
**File:** `backend/app/services/cache.py` — Line 13

```python
# BUGGY
cache_key = f"revenue:{property_id}"

# FIXED
cache_key = f"revenue:{tenant_id}:{property_id}"
```

**What happens:**
Both tenants share `prop-001` in the database (valid — composite PK).
When Ocean Rentals loads first → $0 gets cached as `revenue:prop-001`.
When Sunset Properties loads → hits cache → sees $0 instead of their real $2,250.

**Client report:** *"Sometimes we see revenue numbers that belong to another company"*

---

## Bug #2 — Float Precision Loss
**File:** `backend/app/api/v1/dashboard.py` — Line 18

```python
# BUGGY
total_revenue_float = float(revenue_data['total'])

# FIXED
from decimal import Decimal, ROUND_HALF_UP
total_revenue_float = float(
    Decimal(str(revenue_data['total'])).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
)
```

**What happens:**
DB stores amounts as `NUMERIC(10,3)` — exact decimal.
`float()` converts to IEEE 754 binary — cannot represent most decimals exactly.

```
DB stores:    4975.500    ← exact
API returns:  4975.5      ← precision lost

333.333 + 333.333 + 333.334 = 999.9999999999999  (float)
                             = 1000.000           (DB NUMERIC — exact)
```

**Client report:** *"Revenue totals are slightly off by a few cents"*

---

## Bug #3 — Monthly Revenue Always Returns Zero
**File:** `backend/app/services/reservations.py` — Line 32

```python
# BUGGY — DB call commented out, placeholder hardcoded
# result = await db.fetch_val(query, property_id, tenant_id, start_date, end_date)
# return result or Decimal('0')
return Decimal('0')  # Placeholder for now until DB connection is finalized

# ALSO BUGGY — timezone-naive datetime
start_date = datetime(year, month, 1)  # treated as UTC, ignores property timezone
```

**What happens:**
Every call returns $0 regardless of actual bookings.
Even if fixed, the date range uses naive UTC — missing Paris-timezone reservations:

```sql
-- res-tz-1: Feb 29 23:30 UTC = March 1 00:30 Paris time
-- UTC query puts it in February → $1,250 missing from March total
'2024-02-29 23:30:00+00'  →  1250.000
```

**Client report:** *"Revenue numbers don't match our records for March"*

---

## Bug #4 — Database Pool Uses Wrong Config (Root Cause)
**File:** `backend/app/core/database_pool.py` — Line 18

```python
# BUGGY — these attributes don't exist in Settings
database_url = f"postgresql+asyncpg://{settings.supabase_db_user}:..."

# FIXED — use the actual database_url from settings
database_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
```

**What happens:**
Pool fails silently on every request → falls back to hardcoded mock data.
Mock data returns identical values for all tenants → masks Bug #1 completely.
All bugs invisible until this is fixed first.

```
mock_data = {
    'prop-001': {'total': '1000.00', 'count': 3},  ← same for ALL tenants
    ...
}
```
