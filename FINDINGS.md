# Revenue Dashboard — Bug Investigation & Fixes

Three distinct bugs, one per reported symptom. All live in the revenue path
(`dashboard.py → services/cache.py → services/reservations.py`); the surrounding
auth/Supabase code is unrelated. A fourth (the DB connection pool) was preventing
the app from querying its own database, and a fifth (a hardcoded property list) was
a privacy issue in the UI labels.

---

## Bug 1 — Cross-tenant data leak (Client B: "numbers that belong to another company")

**Root cause.** `services/cache.py` built the Redis key from the property ID alone:

```python
cache_key = f"revenue:{property_id}"      # BUG
```

Property IDs are only unique *within* a tenant — `database/schema.sql` declares
`PRIMARY KEY (id, tenant_id)`, and the seed gives **`prop-001` to both tenants**
(tenant-a "Beach House Alpha", tenant-b "Mountain Lodge Beta"). Whichever tenant
queried `prop-001` first populated the cache; for the next 5 minutes (the TTL)
the *other* tenant got a cache hit and was served the first tenant's revenue.
The underlying SQL was correctly tenant-filtered — the leak was purely the shared
cache key, which is why it appeared intermittently ("sometimes when we refresh").

**Fix.** Scope the key by tenant:

```python
cache_key = f"revenue:{tenant_id}:{property_id}"
```

Old keys simply age out via the existing 5-minute TTL.

---

## Bug 2 — March totals don't match (Client A: timezone)

**Root cause.** `services/reservations.calculate_monthly_revenue` built the month
window from **naive** datetimes and compared them against `check_in_date`, which is
a `TIMESTAMP WITH TIME ZONE` stored in UTC:

```python
start_date = datetime(year, month, 1)     # naive -> treated as UTC  # BUG
```

Properties live in different timezones (`properties.timezone`, e.g. `Europe/Paris`).
The seed's `res-tz-1` checks in at **2024-02-29 23:30 UTC**, which is
**2024-03-01 00:30 in Paris** — March in the client's books. But the naive UTC
window (`>= 2024-03-01 00:00 UTC`) excluded it, dropping €1,250 of revenue out of
March and into February. Reservations near a month boundary were bucketed into the
wrong month.

**Fix.** Anchor the month window to the **property's** timezone, then convert the
boundaries to UTC for the query (using `pytz`, already a dependency):

```python
tz = pytz.timezone(tz_name)               # property's IANA timezone
start_local = tz.localize(datetime(year, month, 1))
start_utc = start_local.astimezone(pytz.UTC)   # 2024-02-29 23:00 UTC for Paris March
```

The function was an unwired placeholder (`return Decimal('0')`); it's now functional
and also receives `tenant_id` (its SQL always referenced a tenant param it was never
given).

---

## Bug 3 — "Off by a few cents" (Finance: precision)

**Root cause.** `api/v1/dashboard.py` converted the money value to a binary float
at the API boundary:

```python
total_revenue_float = float(revenue_data['total'])   # BUG
```

`total_amount` is `NUMERIC(10,3)` (sub-cent precision). Pushing exact Decimal sums
through `float` reintroduces binary representation error — the "few cents here and
there," and exactly what trips the frontend's built-in **"Precision Mismatch
Detected"** banner.

**Fix.** Keep the value as `Decimal`, round to whole cents **once**, and serialize as
a string so the exact value reaches the client:

```python
total_revenue = Decimal(revenue_data['total']).quantize(Decimal("0.01"), ROUND_HALF_UP)
return {"total_revenue": str(total_revenue), ...}
```

The frontend (`RevenueSummary.tsx`) now types `total_revenue` as `string` and parses
it with `Number()` only for display/formatting.

---

## Bug 4 — Database pool never connected (the bug hiding the others)

**Root cause.** `core/database_pool.py` built its connection URL from
`settings.supabase_db_user/password/host/port/name` — fields that **don't exist** on
`Settings` (config.py only defines `database_url`). Every request therefore raised
`'Settings' object has no attribute 'supabase_db_user'`, the pool disabled itself,
and `calculate_total_revenue` fell back to the **mock data** block. That mock is keyed
by `property_id` only, so `prop-001` returned the *same* `1000.00 / 3` to **both**
tenants — a second cross-tenant leak — and the app never touched its own seeded
Postgres (so the timezone/precision data couldn't surface either).

A second, latent bug sat right behind it: `get_session` was declared `async def` but
callers use `async with db_pool.get_session()`, which made them enter a *coroutine*
("'coroutine' object does not support the asynchronous context manager protocol").

**Fix (`core/database_pool.py`).**
- Build the engine URL from `settings.database_url`, swapping the driver to
  `postgresql+asyncpg`.
- Drop `poolclass=QueuePool` (the sync pool is rejected by `create_async_engine`).
- Make `get_session` a plain method returning the `AsyncSession` (the real async
  context manager).

With this, the seeded database is actually queried and the tenant-filtered SQL +
tenant-scoped cache deliver correct, isolated results.

---

## Verifying the fixes (demo) — observed live

```bash
docker compose up --build      # all 4 services: backend, frontend, db, redis
```

Verified end-to-end through the running API (login → `/api/v1/dashboard/summary`):

- **Privacy / isolation:** request `prop-001` as Client A *first* (populates cache),
  then as Client B:
  - A → `total_revenue: "2250.00"`, `reservations_count: 4`
  - B → `total_revenue: "0.00"`,  `reservations_count: 0`  ← no longer A's numbers
- **Timezone:** `calculate_monthly_revenue('prop-001','tenant-a', 3, 2024)` →
  **2250.000** (includes `res-tz-1`); the old naive-UTC window → **1000.000** (dropped
  it). The 1250.000 gap is exactly Client A's March discrepancy.
- **Precision:** `total_revenue` is returned as an exact-cent string (e.g. `"2250.00"`,
  `"4975.50"`); no float drift, and the UI's "Precision Mismatch" banner stays off.

---

## Bug 5 — Property dropdown was hardcoded to Client A (not tenant-aware)

**Root cause.** `frontend/src/components/Dashboard.tsx` hardcoded the property list
using Client A's names/ids (`prop-001 "Beach House Alpha"`, plus `prop-002/003`
which belong only to tenant-a). Every tenant saw that same list, so Client B was
shown Client A's property names (B's `prop-001` is really "Mountain Lodge Beta") and
properties it doesn't own. Revenue figures were already isolated; the *labels* were
not.

**Fix.**
- Backend: new tenant-scoped endpoint `GET /api/v1/properties` (`api/v1/properties.py`
  + `services/properties.py`) returning `[{id, name, timezone}]` filtered by the JWT's
  tenant_id. On DB error it returns `[]` — never shared/hardcoded data.
- Frontend: `Dashboard.tsx` now loads the list via `SecureAPI.getProperties()` with
  loading/error/empty states, and selects the first property.

**Verified live:** `GET /api/v1/properties`
- Client A → Beach House Alpha, City Apartment Downtown, Country Villa Estate (Europe/Paris)
- Client B → Mountain Lodge Beta, Lakeside Cottage, Urban Loft Modern (America/New_York)

**Scope note.** This is a fix to an existing privacy/correctness defect (one tenant
shown another tenant's property names), not new functionality — and it stays within
the existing patterns: the endpoint mirrors `dashboard.py` (same `authenticate_request`
dependency and `DatabasePool` query style) and the client reuses `SecureAPI.request`.
