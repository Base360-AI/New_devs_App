# Revenue Dashboard — Debugging Findings

Four defects, all in the revenue read path. Three of them explain the client reports
directly; the fourth is why the numbers were fabricated rather than merely wrong.

## Reproduction environment

```bash
docker compose up --build
```

Seed data lives in `database/seed.sql`. The two accounts from `ASSIGNMENT.md` map to
`tenant-a` (Sunset Properties) and `tenant-b` (Ocean Rentals) via `backend/app/api/v1/login.py`.

The key property of the dataset: **`prop-001` exists for both tenants.** For `tenant-a`
it is "Beach House Alpha" (Europe/Paris, 4 reservations); for `tenant-b` it is
"Mountain Lodge Beta" (America/New_York, 0 reservations). `properties` has
`PRIMARY KEY (id, tenant_id)`, so a property ID alone identifies nothing.

---

## Bug 1 — Revenue never came from the database

`backend/app/core/database_pool.py` built its DSN from `settings.supabase_db_user`,
`settings.supabase_db_host`, and three other fields that **do not exist** on `Settings`
(`backend/app/config.py`). Initialisation raised `AttributeError`, was swallowed by the
`except` block, and left `session_factory = None`.

Two further faults in the same file:

- `poolclass=QueuePool` is a synchronous pool and cannot be used with `create_async_engine`.
- `get_session()` was `async def`, but every caller used `async with pool.get_session()`.
  `async with` on a coroutine object fails — a coroutine has no `__aenter__`.

So `calculate_total_revenue` always fell into its exception handler, which returned a
**hardcoded dictionary keyed only by `property_id`**:

```python
mock_data = {'prop-001': {'total': '1000.00', 'count': 3}, ...}
```

That dictionary has no notion of tenant. Both companies asking for `prop-001` were served
the same `1000.00`.

**Fix**: derive the DSN from `settings.database_url` (which docker-compose already sets),
convert `postgresql://` → `postgresql+asyncpg://`, drop the explicit `poolclass`, make
`get_session()` synchronous, add an `async with pool.session()` context manager and a
lazy `ensure_initialized()`. The mock fallback is deleted — see Bug 4.

## Bug 2 — Cross-tenant cache poisoning (Client B's privacy report)

`backend/app/services/cache.py`:

```python
cache_key = f"revenue:{property_id}"      # no tenant
```

Whichever tenant queried `prop-001` first populated that key, and the other tenant was
served those figures for the full 300-second TTL. Refreshing the page after the TTL
expired flipped the result — exactly the "sometimes when we refresh we see another
company's numbers" symptom.

**Fix**: key on `revenue:{tenant_id}:{property_id}:{period}`, and refuse to serve a
summary at all when `tenant_id` is empty. `backend/app/api/v1/dashboard.py` also had a
`"default_tenant"` fallback that collapsed every unattributed request into one shared
bucket; that now returns `403`.

## Bug 3 — Month boundaries computed in UTC (Client A's March discrepancy)

`calculate_monthly_revenue` built naive boundaries and compared them against a
`TIMESTAMP WITH TIME ZONE` column:

```python
start_date = datetime(year, month, 1)     # no timezone
```

Reservation `res-tz-1` checks in at `2024-02-29 23:30:00+00`. Beach House Alpha is in
`Europe/Paris`, where that instant is **2024-03-01 00:30 local**. The client books it in
March; a naive UTC comparison files it under February. That single stay is worth
`1250.00` — the whole discrepancy.

**Fix**: filter on the property's local calendar by joining `properties` and comparing
`check_in_date AT TIME ZONE p.timezone` against naive local bounds. Postgres carries its
own tz database, so DST transitions are handled for free.

Verified:

| Query | Result |
|---|---|
| `prop-001`, tenant-a, March 2024 | `2250.00`, 4 reservations |
| `prop-001`, tenant-a, February 2024 | `0.00`, 0 reservations |

## Bug 4 — Decimal money passed through binary floating point

`backend/app/api/v1/dashboard.py` did `float(revenue_data['total'])` on a
`NUMERIC(10, 3)` aggregate, and `RevenueSummary.tsx` then did
`Math.round(data.total_revenue * 100) / 100`.

With the current seed those conversions happen to round-trip cleanly, so this is a latent
defect rather than one you can read off today's dashboard. It is still wrong by
construction: an exact decimal ledger value is rebound to the nearest IEEE-754 double
before anyone sees it, and there is no guarantee the next value survives that.

The cent-level risk the finance team described is real and lives one step away — in
*when* you round. The schema stores three decimals deliberately
("to allow sub-cent precision tracking") and `prop-001` carries `333.333 + 333.333 + 333.334`:

| Strategy | Result |
|---|---|
| Round each reservation, then sum | `2249.99` |
| Sum at full precision, round once | `2250.00` |

**Fix**: sum in SQL at full `NUMERIC` precision, quantize once with `ROUND_HALF_UP`,
and send the value as a **decimal string**. The frontend formats that string with pure
string manipulation — no `parseFloat`, no `* 100`. The mock fallback is gone entirely:
a visible `503` beats a plausible wrong number on a finance dashboard.

Currency was also hardcoded to `"USD"` while `reservations.currency` exists; it is now
read from the data, and a property holding reservations in more than one currency raises
instead of summing them into a meaningless total.

---

## Verification

Cold cache, tenant B queries `prop-001` first, then tenant A:

```
tenant-b  prop-001 → 0.00     (0 reservations)   Mountain Lodge Beta
tenant-a  prop-001 → 2250.00  (4 reservations)   Beach House Alpha
```

Full isolation matrix:

| Property | tenant-a | tenant-b |
|---|---|---|
| prop-001 | 2250.00 (4) | 0.00 (0) |
| prop-002 | 4975.50 (4) | 0.00 (0) |
| prop-003 | 6100.50 (2) | 0.00 (0) |
| prop-004 | 0.00 (0) | 1776.50 (4) |
| prop-005 | 0.00 (0) | 3256.00 (3) |

Redis now holds `revenue:tenant-a:prop-001:all` and `revenue:tenant-b:prop-001:all` as
separate entries.

Note how the old mock returned `1000.00 / 3 reservations` for `prop-001`: that is the
real total *minus* the timezone-boundary reservation. The placeholder data had been
generated with the same UTC bug baked in.

## Not changed

- No schema changes, no new services, no dependency additions.
- `.gitignore` added: the `./backend:/app` bind mount makes the container write
  root-owned `__pycache__` directories into the working tree.
