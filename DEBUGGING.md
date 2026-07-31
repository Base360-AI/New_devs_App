# Debugging Walkthrough

How each bug was located with the debugger, and how to reproduce that session.

## Setup

The backend runs locally against the Postgres and Redis containers. Breakpoints
work immediately, with no attach step.

```bash
# 1. Data services
docker compose up -d db redis

# 2. Backend (needs Python 3.10+; the codebase uses `str | None` syntax)
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
DATABASE_URL="postgresql://postgres:postgres@localhost:5433/propertyflow" \
REDIS_URL="redis://localhost:6380/0" \
SECRET_KEY="debug_challenge_secret" \
.venv/bin/python -m uvicorn app.main:app --port 8000

# 3. Frontend
cd frontend && npm run dev
```

In VS Code, hit F5 on **"Python: Debug Backend (local)"** instead of step 2 — it
sets those environment variables for you.

Frontend: http://localhost:5173 · API docs: http://localhost:8000/docs

<details>
<summary>Running everything in Docker instead</summary>

```bash
docker compose -f docker-compose.yml -f docker-compose.debug.yml up --build
```

Then attach with **"Python: Attach to Backend (Docker)"**. If image pulls fail with
`lookup auth.docker.io: i/o timeout`, Docker Desktop's internal DNS is the problem —
add `"dns": ["8.8.8.8", "1.1.1.1"]` under Settings → Docker Engine and restart.
</details>

| Client | Email | Password | Tenant |
|---|---|---|---|
| Sunset Properties | `sunset@propertyflow.com` | `client_a_2024` | `tenant-a` |
| Ocean Rentals | `ocean@propertyflow.com` | `client_b_2024` | `tenant-b` |

To see the **broken** behaviour first, stash the fixes, then restore them:

```bash
git stash            # back to the buggy code
git stash pop        # fixes restored
```

---

## Bug 1 — Client B sees another company's revenue

**Breakpoint:** `backend/app/services/cache.py` → the `cached = await redis_client.get(cache_key)` line.

**Session:**
1. Log in as **Sunset**, open `prop-001`. Breakpoint hits.
   Inspect: `tenant_id == 'tenant-a'`, `cache_key == 'revenue:prop-001'`, `cached is None`.
   The result gets written to Redis under that key. Continue.
2. Log in as **Ocean**, open `prop-001`. Breakpoint hits again.
   Inspect: `tenant_id == 'tenant-b'` — but `cache_key` is **the same string**, and `cached` is now **populated**.

**The smoking gun.** Add this watch expression:

```python
json.loads(cached)['tenant_id'] != tenant_id
```

It evaluates to `True` — the cached payload is stamped `tenant-a` while the request is `tenant-b`. Ocean is served Sunset's numbers and returns before any tenant-filtered query runs.

**Root cause:** `cache_key = f"revenue:{property_id}"` omits the tenant. Property IDs are only unique *per tenant* (`properties` has a composite `(id, tenant_id)` key) and `prop-001` exists for both companies.

**Fix:** `cache_key = f"revenue:{tenant_id}:{property_id}"`. Re-run: keys become `revenue:tenant-a:prop-001` and `revenue:tenant-b:prop-001`, `cached` is `None` for Ocean, and the leak is gone.

---

## Bug 2 — Client A's March totals don't match

**Breakpoint:** `backend/app/services/reservations.py` → `calculate_monthly_revenue`, on the line after `end_date` is computed.

**Session:** Inspect `start_date` and `end_date`.

- Before: `2024-03-01 00:00:00` — naive, i.e. implicitly **UTC**.
- After: `2024-02-29 23:00:00+00:00` — March 1st *in Paris* (UTC+1) is Feb 29th 23:00 UTC.

Now step to the query result and compare:

| Month boundaries | March 2024 total | bookings |
|---|---|---|
| UTC (before) | `1000.000` | 3 |
| `Europe/Paris` (after) | `2250.000` | 4 |

**The missing booking:** `res-tz-1`, `total_amount = 1250.000`, checking in `2024-02-29 23:30:00+00` UTC — which is `2024-03-01 00:30` in Paris. It *is* a March booking for this property, but UTC bucketing files it under February.

**Root cause:** month boundaries were built with naive `datetime(year, month, 1)` while `properties.timezone` (here `Europe/Paris`) was ignored.

**Fix:** compute the boundaries in the property's own timezone and convert to UTC before filtering.

---

## Bug 3 — Finance: totals off by a few cents

**Breakpoint:** `backend/app/api/v1/dashboard.py` → the line building `total_revenue`.

**Session:** `total_amount` is `NUMERIC(10,3)`, so sums can carry a third decimal. In the Debug Console, evaluate a half-cent value:

```python
float('1080.405')                                             # 1080.405
round(1080.405 * 100) / 100                                   # 1080.4   <-- loses a cent
Decimal('1080.405').quantize(Decimal('0.01'), ROUND_HALF_UP)  # 1080.41  <-- correct
```

The old path rounded **twice** in binary floating point — `float()` in `dashboard.py`, then `Math.round(x * 100) / 100` again in `RevenueSummary.tsx`. Because `1080.405` isn't exactly representable in binary, it sits just *below* the true half and rounds down.

**Fix:** quantize with `Decimal` + `ROUND_HALF_UP` on the backend, and drop the frontend's redundant re-rounding. Frontend breakpoint to confirm: `frontend/src/components/RevenueSummary.tsx`, on the `displayTotal` line.

---

## Bug 4 — The dashboard was never reading the database

Found while stepping into Bug 1: the tenant-filtered SQL never executed.

**Breakpoint:** `backend/app/core/database_pool.py` → the `except Exception as e:` block in `initialize()`.

It is hit on **every** request. Inspect `e`:

```
AttributeError: 'Settings' object has no attribute 'supabase_db_user'
```

`initialize()` built its URL from `settings.supabase_db_user/password/host/port/name`, none of which exist in `app/config.py` — it only defines `database_url`. So `session_factory` was always `None`.

**Then set a breakpoint on the old `except` block in `calculate_total_revenue`** (`reservations.py`). Also hit every request, with `e = "Database pool not available"`, about to return from a hardcoded `mock_data` dict keyed **only by `property_id`**:

```python
mock_data['prop-001']   # {'total': '1000.00', 'count': 3}  -- for BOTH tenants
```

This was the real engine behind Client B's complaint, and note `1000.00 / 3` is *exactly* the wrong UTC-bucketed March figure from Bug 2 — the buggy answer had been frozen into a constant.

**Two further defects** surfaced on the way to fixing it:
- `poolclass=QueuePool` → `ArgumentError: Pool class QueuePool cannot be used with asyncio engine`. Needs `AsyncAdaptedQueuePool`.
- `async def get_session()` used as `async with db_pool.get_session()` → `AttributeError: __aenter__`, because calling it returns a coroutine, not a session.

**Fix:** build the URL from `settings.database_url`, use `AsyncAdaptedQueuePool`, make `get_session()` non-async, reuse the shared `db_pool` singleton instead of constructing a new engine per request, and **delete the fabricated fallback** — the endpoint now returns `503` rather than displaying revenue it cannot attribute to real data.

---

## Verifying the fixes

Log in as each client and compare `prop-001`:

| | Sunset (tenant-a) | Ocean (tenant-b) |
|---|---|---|
| Before | `1000.00`, 3 bookings | `1000.00`, 3 bookings ← Sunset's data |
| After | `2250.00`, 4 bookings | `0.00`, 0 bookings |

Ocean's `prop-001` (*Mountain Lodge Beta*) genuinely has no reservations — `0.00` is the correct answer, and the fact that it previously showed `1000.00` was the privacy breach.

Confirm cache isolation directly:

```bash
docker compose exec redis redis-cli KEYS 'revenue:*'
# revenue:tenant-a:prop-001
# revenue:tenant-b:prop-001
```
