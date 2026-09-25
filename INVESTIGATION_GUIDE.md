# Bug Investigation & Fix Guide
## Flex Property Revenue Dashboard — Technical Assignment

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Environment Setup](#2-environment-setup)
3. [Bug #1 — Cross-Tenant Cache Leak (Privacy)](#3-bug-1--cross-tenant-cache-leak-privacy)
4. [Bug #2 — Floating-Point Revenue Precision](#4-bug-2--floating-point-revenue-precision)
5. [Bug #3 — Monthly Revenue Always Returns Zero](#5-bug-3--monthly-revenue-always-returns-zero)
6. [Bonus — Hardcoded Property List Leaks Tenant Structure](#6-bonus--hardcoded-property-list-leaks-tenant-structure)
7. [Fix Summary Table](#7-fix-summary-table)
8. [Loom Video Script](#8-loom-video-script)
9. [CTO Interview Talking Points](#9-cto-interview-talking-points)

---

## 1. System Overview

### Architecture

```
Browser (React/TypeScript)
    ↓  JWT Bearer token
FastAPI Backend (Python)
    ↓  SQL queries with tenant_id filter
PostgreSQL (multi-tenant, one DB)
    ↑  Redis (revenue cache, 5-min TTL)
```

### Multi-Tenant Model

The system serves multiple property management companies ("tenants") from a single database. Isolation is enforced by:

- A `tenant_id` column on `properties` and `reservations` tables
- Row Level Security (RLS) enabled on both tables
- JWT authentication that carries the user's `tenant_id` in the token payload
- Backend query filters: `WHERE property_id = :id AND tenant_id = :tenant_id`

### Test Credentials

| Client | Email | Password | Tenant ID |
|--------|-------|----------|-----------|
| Sunset Properties | sunset@propertyflow.com | client_a_2024 | tenant-a |
| Ocean Rentals | ocean@propertyflow.com | client_b_2024 | tenant-b |

### Key Seed Data

```sql
-- BOTH tenants deliberately share property ID "prop-001"
-- This is valid (composite PK: id + tenant_id) but exposes the cache bug
('prop-001', 'tenant-a', 'Beach House Alpha',    'Europe/Paris')
('prop-001', 'tenant-b', 'Mountain Lodge Beta',  'America/New_York')

-- Tenant-A intentional sub-cent amounts (triggers precision bug)
('res-dec-1', 'prop-001', 'tenant-a', ..., 333.333)
('res-dec-2', 'prop-001', 'tenant-a', ..., 333.333)
('res-dec-3', 'prop-001', 'tenant-a', ..., 333.334)
-- DB NUMERIC sum = exactly 1000.000

-- Timezone edge-case reservation for tenant-a
-- check_in: 2024-02-29 23:30 UTC = 2024-03-01 00:30 Paris time
('res-tz-1', 'prop-001', 'tenant-a', '2024-02-29 23:30:00+00', ..., 1250.000)
```

---

## 2. Environment Setup

```bash
# Clone / open the forked repo
cd /path/to/New_devs_App

# Start all services (backend, frontend, postgres, redis)
docker-compose up --build

# Verify services are healthy
# Frontend: http://localhost:3000
# Backend docs: http://localhost:8000/docs
# PostgreSQL: localhost:5433
# Redis: localhost:6380
```

Expected startup output:
```
db        | database system is ready to accept connections
redis     | Ready to accept connections
backend   | Application startup complete.
frontend  | nginx started
```

---

## 3. Bug #1 — Cross-Tenant Cache Leak (Privacy)

### Client Report
> *"Sometimes when we refresh the page, we see revenue numbers that look like they belong to another company."* — Ocean Rentals (Client B)

### Root Cause

**File:** `backend/app/services/cache.py`, **Line 13**

```python
# BUGGY CODE
async def get_revenue_summary(property_id: str, tenant_id: str) -> Dict[str, Any]:
    cache_key = f"revenue:{property_id}"   # ← tenant_id is passed in but IGNORED

    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)           # ← could be another tenant's data!

    result = await calculate_total_revenue(property_id, tenant_id)
    await redis_client.setex(cache_key, 300, json.dumps(result))
    return result
```

The function accepts `tenant_id` as a parameter but never uses it in the cache key. The key is just `revenue:{property_id}`.

### Why It Leaks

The seed data has **both tenants sharing the same property ID** (`prop-001`):

```
prop-001 → tenant-a (Beach House Alpha)    revenue: $2,250.000
prop-001 → tenant-b (Mountain Lodge Beta)  revenue: $0.00 (no reservations)
```

**Scenario A — Client B sees Client A's money:**
1. Client A (Sunset) queries `prop-001` → DB returns $2,250 → cached as `revenue:prop-001`
2. Client B (Ocean) queries `prop-001` → Redis **cache hit** → returns `$2,250` (Client A's data)
3. Client B sees revenue that doesn't belong to them ❌

**Scenario B — Client A sees zero:**
1. Client B queries `prop-001` first → DB returns $0 → cached as `revenue:prop-001`
2. Client A queries `prop-001` → cache hit → returns `$0` instead of `$2,250`
3. Client A's board meeting numbers are wrong ❌

The 5-minute TTL means this changes on every cache expiry — hence the "sometimes" behaviour.

### How to Reproduce

```bash
# Terminal 1 — watch Redis in real time
docker exec -it $(docker ps -qf "name=redis") redis-cli monitor

# Browser tab 1: log in as ocean@propertyflow.com, open Dashboard, select prop-001
# Browser tab 2: log in as sunset@propertyflow.com, open Dashboard, select prop-001
# Refresh both tabs repeatedly — one will show the other's revenue
```

### The Fix

**File:** `backend/app/services/cache.py`, **Line 13**

```python
# FIXED CODE — include tenant_id in the cache key
cache_key = f"revenue:{tenant_id}:{property_id}"
```

**Before:** `revenue:prop-001`
**After:** `revenue:tenant-a:prop-001` and `revenue:tenant-b:prop-001` are separate keys — total isolation.

```python
# Full fixed function
async def get_revenue_summary(property_id: str, tenant_id: str) -> Dict[str, Any]:
    cache_key = f"revenue:{tenant_id}:{property_id}"   # ← FIXED

    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    from app.services.reservations import calculate_total_revenue
    result = await calculate_total_revenue(property_id, tenant_id)
    await redis_client.setex(cache_key, 300, json.dumps(result))
    return result
```

### Why This Is the Correct Fix

- The `tenant_id` is already trusted (extracted from the signed JWT, not user input)
- Redis key namespacing is the standard pattern for multi-tenant caching
- Zero performance cost — same O(1) Redis lookup
- The fix is minimal and surgical — no logic change, only the key string

---

## 4. Bug #2 — Floating-Point Revenue Precision

### Client Report
> *"Revenue totals are slightly off by a few cents."* — Finance Team

### Root Cause

**File:** `backend/app/api/v1/dashboard.py`, **Line 18**

```python
# BUGGY CODE
revenue_data = await get_revenue_summary(property_id, tenant_id)
total_revenue_float = float(revenue_data['total'])   # ← precision loss here

return {
    "property_id": revenue_data['property_id'],
    "total_revenue": total_revenue_float,            # ← float sent to frontend
    ...
}
```

### Why It Loses Precision

The database stores `total_amount` as `NUMERIC(10, 3)` — exact decimal arithmetic with 3 decimal places. Python's `Decimal` type preserves this. But `float()` converts to IEEE 754 binary floating point, which **cannot exactly represent most decimal fractions**.

```
NUMERIC in DB:   333.333 (exact)
Python Decimal:  Decimal('333.333') (exact)
Python float:    333.33299999999997726... (approximation)
```

The data is specifically designed to expose this:
```
333.333 + 333.333 + 333.334 = 1000.000  (exact NUMERIC arithmetic in PostgreSQL)

After float conversion:
333.333... + 333.333... + 333.334... ≈ 999.9999... or 1000.0000001...
```

The frontend then does:
```typescript
// RevenueSummary.tsx line 64
const displayTotal = Math.round(data.total_revenue * 100) / 100;
```

If `data.total_revenue` is `999.9999999999999`, then:
- `999.9999999999999 * 100 = 99999.99999999999`
- `Math.round(99999.99999999999) = 100000`
- `100000 / 100 = 1000.00` ← looks OK here

But with different amounts this can produce visible cent-level errors, and the precision mismatch warning built into the UI confirms this is an intentional test:

```tsx
{/* RevenueSummary.tsx line 107 — built-in precision warning! */}
{Math.abs(data.total_revenue - displayTotal) > 0.000001 && showRaw && (
    <div>Precision Mismatch Detected</div>
)}
```

The frontend even has a "Precision Mismatch Detected" warning — this was placed there deliberately as a hint.

### The Fix

**File:** `backend/app/api/v1/dashboard.py`, **Line 18**

```python
# FIXED CODE — round at the Decimal level before converting
from decimal import Decimal, ROUND_HALF_UP

total_revenue_decimal = Decimal(str(revenue_data['total'])).quantize(
    Decimal('0.01'), rounding=ROUND_HALF_UP
)
total_revenue_float = float(total_revenue_decimal)
```

**Why `ROUND_HALF_UP`?** Financial calculations conventionally round half-cents up (e.g. $1.005 → $1.01). This matches client expectations and accounting standards.

**Why not just fix it in the frontend?** The backend should be the source of truth for financial data. Sending an imprecise float to the API means any consumer (mobile app, external integrations) would also get wrong data.

---

## 5. Bug #3 — Monthly Revenue Always Returns Zero

### Client Report
> *"The revenue numbers don't match our internal records. We're showing different totals for March."* — Sunset Properties (Client A)

### Root Cause — Part A: Placeholder Never Implemented

**File:** `backend/app/services/reservations.py`, **Line 32**

```python
# BUGGY CODE
async def calculate_monthly_revenue(property_id: str, month: int, year: int, db_session=None) -> Decimal:
    start_date = datetime(year, month, 1)
    if month < 12:
        end_date = datetime(year, month + 1, 1)
    else:
        end_date = datetime(year + 1, 1, 1)

    # SQL query is written but COMMENTED OUT — never runs
    query = """
        SELECT SUM(total_amount) as total
        FROM reservations
        WHERE property_id = $1
        AND tenant_id = $2
        AND check_in_date >= $3
        AND check_in_date < $4
    """

    # result = await db.fetch_val(query, property_id, tenant_id, start_date, end_date)
    # return result or Decimal('0')

    return Decimal('0')   # ← ALWAYS returns zero. This is a placeholder, never finished.
```

The developer wrote the SQL and date logic, then left the DB call commented out with a placeholder. Every call to `calculate_monthly_revenue` returns `$0` regardless of actual reservations.

### Root Cause — Part B: Timezone-Naive Datetimes

Even if the query were uncommented and run, it has a timezone bug:

```python
start_date = datetime(year, month, 1)   # ← naive datetime, no timezone info
```

When compared against `TIMESTAMP WITH TIME ZONE` columns in PostgreSQL, a naive Python `datetime` is treated as **UTC**. But Sunset Properties' properties are in `Europe/Paris` (UTC+1 in winter, UTC+2 in summer).

**The seed data has an intentional timezone edge case:**
```sql
-- res-tz-1: check_in = 2024-02-29 23:30:00+00 UTC
--           = 2024-03-01 00:30:00 Paris time  ← this IS a March reservation in Paris!
```

With the naive UTC date range for March 2024:
```
start_date = 2024-03-01 00:00:00 (UTC)
```

The query `check_in_date >= '2024-03-01 00:00:00'` in UTC **excludes** `res-tz-1` (which check_in is `2024-02-29 23:30 UTC`).

But from the client's Paris-timezone perspective, that reservation **is** in March. So their internal records count it for March, but the API doesn't. **This is exactly the mismatch Sunset Properties reported.**

### The Fix — Part A: Implement the query

```python
# FIXED CODE
async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Decimal:
    from app.core.database_pool import DatabasePool
    from sqlalchemy import text

    db_pool = DatabasePool()
    await db_pool.initialize()

    if month < 12:
        start_date = datetime(year, month, 1)
        end_date = datetime(year, month + 1, 1)
    else:
        start_date = datetime(year, month, 1)
        end_date = datetime(year + 1, 1, 1)

    async with db_pool.get_session() as session:
        query = text("""
            SELECT COALESCE(SUM(r.total_amount), 0) as total
            FROM reservations r
            JOIN properties p ON r.property_id = p.id AND r.tenant_id = p.tenant_id
            WHERE r.property_id = :property_id
              AND r.tenant_id   = :tenant_id
              AND (r.check_in_date AT TIME ZONE p.timezone) >= :start_date
              AND (r.check_in_date AT TIME ZONE p.timezone) <  :end_date
        """)
        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id":   tenant_id,
            "start_date":  start_date,
            "end_date":    end_date,
        })
        row = result.fetchone()
        return Decimal(str(row.total)) if row else Decimal('0')
```

### The Fix — Part B: Timezone-aware date comparison

The key change in the SQL:
```sql
-- BEFORE (wrong — naive UTC comparison)
AND check_in_date >= :start_date

-- AFTER (correct — convert to property's local timezone first)
AND (check_in_date AT TIME ZONE p.timezone) >= :start_date
```

`AT TIME ZONE p.timezone` converts the UTC timestamp to the property's local time before comparing, so a midnight-Paris reservation is counted in March, not February.

---

## 6. Bonus — Hardcoded Property List Leaks Tenant Structure

### Issue

**File:** `frontend/src/components/Dashboard.tsx`, **Lines 4–10**

```typescript
// ALL 5 properties hardcoded for ALL users — regardless of tenant
const PROPERTIES = [
  { id: 'prop-001', name: 'Beach House Alpha' },        // tenant-a
  { id: 'prop-002', name: 'City Apartment Downtown' },  // tenant-a
  { id: 'prop-003', name: 'Country Villa Estate' },     // tenant-a
  { id: 'prop-004', name: 'Lakeside Cottage' },         // tenant-b  ← shown to tenant-a!
  { id: 'prop-005', name: 'Urban Loft Modern' },        // tenant-b  ← shown to tenant-a!
];
```

**Impact:** Client A (Sunset) can see and select Client B's property names in the dropdown. While the backend correctly scopes the revenue query by `tenant_id`, this still leaks structural information (property names, IDs) across tenants, and allows any client to query any property ID.

### The Fix

Fetch the property list from the backend (which is already tenant-scoped) instead of hardcoding it:

```typescript
// FIXED Dashboard.tsx — fetch properties from API
const [properties, setProperties] = useState<Property[]>([]);

useEffect(() => {
  SecureAPI.getProperties().then(res => setProperties(res.data || []));
}, []);
```

The backend's `/api/v1/properties` endpoint filters by the authenticated user's `tenant_id`, so each client only sees their own properties.

---

## 7. Fix Summary Table

| # | Severity | File | Line | Bug | Fix |
|---|----------|------|------|-----|-----|
| 1 | **Critical** | `backend/app/services/cache.py` | 13 | Cache key missing `tenant_id` — cross-tenant data leak | `f"revenue:{tenant_id}:{property_id}"` |
| 2 | **High** | `backend/app/api/v1/dashboard.py` | 18 | `float()` conversion of `Decimal` loses sub-cent precision | Round with `Decimal.quantize(ROUND_HALF_UP)` before casting |
| 3 | **High** | `backend/app/services/reservations.py` | 32 | Monthly revenue always returns `0` (placeholder), timezone-naive dates | Implement DB query; use `AT TIME ZONE` in SQL |
| 4 | **Medium** | `frontend/src/components/Dashboard.tsx` | 4–10 | All properties hardcoded for all tenants | Fetch from tenant-scoped API endpoint |

---

## 8. Loom Video Script

**Target length: 6–8 minutes. Keep it concise — one bug per chapter.**

---

### Intro (30 seconds)

> "Hi, I'm [Name]. I investigated the Flex property revenue dashboard and found three bugs — one critical privacy issue, one financial precision bug, and one unimplemented feature with a timezone flaw. I'll show you each bug, where it lives in the code, and the fix."

---

### Chapter 1 — Bug #1: Privacy Leak (2 minutes)

**Screen: browser with two tabs**

1. Open two incognito windows side by side
2. Log in as `sunset@propertyflow.com` in one, `ocean@propertyflow.com` in the other
3. Select `prop-001` in both dashboards
4. Refresh repeatedly — show one client seeing the other's revenue

**Screen: VS Code — `cache.py` line 13**

> "Here's the cause. The `get_revenue_summary` function takes a `tenant_id` parameter — you can see it right here in the signature — but line 13 builds the Redis key using only the property ID. `tenant_id` is completely ignored. Both tenants share `prop-001` in the database — that's intentional, the schema uses a composite primary key. So one tenant's revenue overwrites the other in the cache."

**Screen: show the one-line fix**

> "The fix is one word — add `tenant_id` to the key string. Now `tenant-a` and `tenant-b` have completely separate cache entries. They can never interfere."

---

### Chapter 2 — Bug #2: Float Precision (1.5 minutes)

**Screen: browser — dashboard with `showRaw` mode or API response in network tab**

> "The seed data has three reservations for `prop-001` — each is $333.333, designed to sum to exactly $1,000.00. Watch the raw API response."

**Screen: VS Code — `dashboard.py` line 18**

> "The database computes the sum in NUMERIC arithmetic — exact. The Python service reads it as a Decimal — still exact. But then this single line — `float(revenue_data['total'])` — converts it to a binary float. IEEE 754 floats can't represent most decimal fractions exactly. $333.333 in float is actually 333.3329999... The frontend then does `Math.round * 100 / 100` which can shift the result by a cent. Interestingly, the frontend component has a 'Precision Mismatch Detected' warning built in — a deliberate hint."

**Screen: show the fix**

> "The fix is to round at the Decimal level before we ever touch float. `Decimal.quantize('0.01', ROUND_HALF_UP)` — this is standard financial rounding, the kind banks use. Only after rounding do we convert to float, so the value going into JSON is already a clean two-decimal number."

---

### Chapter 3 — Bug #3: Monthly Revenue Returns Zero (2 minutes)

**Screen: VS Code — `reservations.py` lines 19–32**

> "This one is interesting — the developer wrote the SQL query, wrote the date range logic, even wrote the commented-out return statement. Then left a placeholder: `return Decimal('0')`. So `calculate_monthly_revenue` has always returned zero for every property, every month, no exceptions."

> "There's a second problem even if we uncomment it. Line 10 creates `datetime(year, month, 1)` — a timezone-naive datetime. PostgreSQL will treat it as UTC. But Sunset Properties' buildings are in Paris — UTC+1 in winter. So a reservation that checks in at 11:30pm on February 29th UTC is actually 12:30am March 1st in Paris. The client's internal system counts it as a March booking. The API, with a naive UTC boundary, misses it. Their March total is wrong by $1,250."

**Screen: show the fixed SQL**

> "The fix joins the properties table to get the timezone, then applies `AT TIME ZONE p.timezone` to the check-in date before comparing. Now the March boundary is March 1st midnight Paris time, not UTC midnight. The reservation is correctly counted."

---

### Closing (30 seconds)

> "To summarise: one-line cache key fix for the privacy bug, one-line Decimal rounding fix for precision, and implementing the stubbed monthly revenue query with proper timezone handling. All three reported issues — Client B's data contamination, Client A's March mismatch, and the finance team's rounding concerns — are now resolved. I've pushed the fixes to my fork."

---

## 9. CTO Interview Talking Points

These are the deeper technical conversations the CTO will likely want to have.

---

### On finding the bugs

**What they might ask:** *"How did you approach the investigation?"*

**Key points:**
- Started with the symptom descriptions and mapped them to system layers (auth → cache → DB → frontend)
- The "sometimes" qualifier on Client B's complaint was the key signal — deterministic bugs don't say "sometimes." That immediately points to shared mutable state: the cache
- Read the seed data carefully — the shared `prop-001` across tenants is intentional, it's the test case
- The `NUMERIC(10,3)` column type and the `float()` cast in the same path is a classic "impedance mismatch" pattern

---

### On Bug #1 — the cache design

**What they might ask:** *"How would you prevent this class of bug in future?"*

**Strong answer:**
- The root cause is that the function signature *looks* correct (accepts `tenant_id`) but silently ignores it. A code review would likely miss this.
- **Structural solution:** Wrap the Redis client in a `TenantScopedCache` class that automatically prepends `tenant_id` to all keys. Tenants can't "forget" to scope — it's enforced by the type.
- **Testing solution:** Write an integration test that queries the same property as two different tenants and asserts the responses are independent. This test would have caught this bug at write-time.
- **TTL consideration:** 5-minute TTL means the bug would manifest and disappear cyclically. Monitoring for "same property, different tenants, same response hash" would catch this in production.

---

### On Bug #2 — financial precision

**What they might ask:** *"When should you use Decimal vs float in financial systems?"*

**Strong answer:**
- **Never use float for money** — this is a hard rule in financial engineering. Float is a tool for scientific computing where approximate answers are fine. Money requires exact decimal arithmetic.
- The right approach: store as `NUMERIC` in the DB (already done here), use Python `Decimal` throughout the service layer, only convert to float at the API boundary, and only after rounding to the display precision.
- Better still: return monetary values as strings (`"2250.00"`) from the API, not numbers. This prevents any language's float parsing from touching the value. The frontend parses the string for display only.
- Libraries like `Money` (Python) or `dinero.js` (JS) enforce correct handling and prevent accidental float arithmetic.

---

### On Bug #3 — the placeholder

**What they might ask:** *"How do you handle unfinished code in a codebase?"*

**Strong answer:**
- Placeholder code that compiles and runs but returns wrong results is more dangerous than a crash. A crash is immediately visible; silent wrong answers erode trust slowly.
- Better patterns: `raise NotImplementedError("monthly revenue: see ticket PROP-142")` — this fails loudly and documents the gap. Or feature-flag the endpoint as disabled until the implementation is complete.
- The timezone bug hiding inside the unfinished code is a good example of why "leave it for later" compounds — the timezone requirement is architectural and easy to miss when added as an afterthought.

---

### On the timezone design

**What they might ask:** *"How would you design timezone handling in a multi-tenant, multi-property system?"*

**Strong answer:**
- Store all timestamps in UTC in the database (already done — `TIMESTAMP WITH TIME ZONE`)
- Store the property's `timezone` identifier as an IANA timezone string (already done — `Europe/Paris`)
- Do timezone conversion **in the SQL query** using `AT TIME ZONE`, not in application code. The database's timezone library is well-tested and handles DST transitions correctly.
- Expose timezone-aware ISO 8601 strings to the frontend (`2024-03-01T00:30:00+01:00`), let the browser format for local display
- For reporting (monthly/annual summaries), always parameterise by timezone — the "March report" for a Paris property and a New York property have different UTC boundaries

---

### On the overall system design

**What they might ask:** *"What else would you look at in this codebase?"*

**Honest but constructive answer:**
- The `tenant_resolver.py` has hardcoded email-to-tenant mappings — this pattern doesn't scale. Tenant resolution should always come from the verified JWT claims, not a lookup table in code.
- The frontend's `RevenueSummary.tsx` hardcodes `activeTenant = 'candidate'` when no override is passed. This sends a debug `X-Simulated-Tenant` header on every request. The backend ignores it, but it's dead code that signals an incomplete tenant simulation feature. It should be removed.
- The `Dashboard.tsx` hardcodes all 5 properties for all tenants — a client sees other tenants' property names in the dropdown. Revenue is still scoped correctly by the backend, but it's an information leak.
- Positive: the `SecureAPI` client in the frontend has good bones — tenant isolation validation, request deduplication, cache invalidation on token change. The architecture intentions are right; some implementations need catching up.

---

### On how you'd prevent these bugs systematically

**What they might ask:** *"What process changes would you recommend?"*

**Strong answer:**
- **Integration tests over unit tests for multi-tenant paths:** A unit test of `calculate_total_revenue` can pass while the cache bug exists. An integration test that logs in as two tenants and cross-checks their data would catch it.
- **Type-safe tenant context:** Use a `TenantContext` object that's propagated explicitly through the call stack, rather than strings passed around. Mypy/type checking can then enforce that tenant-scoped operations always receive a context.
- **Financial amounts as value objects:** A `Money(amount=Decimal, currency=str)` type prevents accidental float conversion — you'd have to explicitly call `.to_float()` and that's a red flag in code review.
- **Code review checklist for caching:** Any new cache write should have `tenant_id` in the key — make it a required item on the PR template for backend changes.
- **Staging environment with cross-tenant smoke tests:** Before any deploy, run a script that logs in as each test tenant, fetches the same property ID from each, and asserts the responses differ.

---

*Guide prepared for Flex technical assignment — September 2025*
