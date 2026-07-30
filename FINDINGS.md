# Revenue Dashboard — Investigation & Fixes

Three client-reported problems, three separate root causes, plus one that made all
of them hard to see. Everything below was reproduced against the seeded database
before and after the fix.

Reproduce with:

```bash
docker compose up --build -d
./scripts/verify_fixes.sh                                    # 19 end-to-end checks
docker compose exec backend python -m pytest tests -q        # 17 unit tests
```

---

## Ground truth

What the seeded database actually contains (`docker compose exec db psql -U postgres -d propertyflow`):

| tenant | property | bookings | revenue |
|---|---|---|---|
| tenant-a (Sunset) | prop-001 Beach House Alpha | 4 | 2250.000 |
| tenant-a | prop-002 City Apartment Downtown | 4 | 4975.500 |
| tenant-a | prop-003 Country Villa Estate | 2 | 6100.500 |
| tenant-b (Ocean) | prop-001 Mountain Lodge Beta | 0 | — |
| tenant-b | prop-004 Lakeside Cottage | 4 | 1776.500 |
| tenant-b | prop-005 Urban Loft Modern | 3 | 3256.000 |

The important detail: **`prop-001` exists for both clients and is a different
building for each.** Property IDs are only unique within a tenant — the schema
says so (`PRIMARY KEY (id, tenant_id)`).

---

## Bug 0 — The dashboard was not reading the database at all

**Symptom:** the numbers were self-consistent but wrong, and nothing anyone did
to the data changed them.

`calculate_total_revenue()` wrapped its query in a `try/except` whose fallback
was a hardcoded dictionary of "mock data for testing". The query never ran:

- `DatabasePool.initialize()` built its DSN from `settings.supabase_db_user`,
  `supabase_db_host` … — fields that do not exist on `Settings`. The
  `AttributeError` was swallowed, leaving `session_factory = None`.
- It also passed the synchronous `QueuePool` to `create_async_engine`, and
  `get_session()` was declared `async def` while callers used it as
  `async with db_pool.get_session()` — an `async with` over a coroutine.
- `DatabasePool()` was re-instantiated per request, so every call built a new
  engine.

Every dashboard request therefore hit `except` and served fabricated figures
(`prop-001 → 1000.00`), logging one line to stdout that nobody was reading.

**Fix** — [`backend/app/core/database_pool.py`](backend/app/core/database_pool.py),
[`backend/app/services/reservations.py`](backend/app/services/reservations.py):
build the DSN from the configured `DATABASE_URL` (re-prefixed for asyncpg), drop
the sync pool class, make `get_session()` synchronous so `async with` gets a
session, use the module-level singleton with an idempotent `initialize()`, and
**delete the mock fallback**. A revenue endpoint that cannot reach its database
must fail loudly, not invent numbers for a board meeting.

---

## Bug 1 — Client B saw another company's revenue (privacy)

**Root cause** — [`backend/app/services/cache.py`](backend/app/services/cache.py):

```python
cache_key = f"revenue:{property_id}"      # no tenant
```

Both clients own a `prop-001`. Whichever tenant missed the cache first wrote its
revenue under the shared key, and for the next 5 minutes the *other* tenant was
served that value. Refreshing after the TTL expired flipped which company's
numbers appeared — exactly the "sometimes when we refresh" report.

**Fix:** the cache key is now `revenue:{tenant_id}:{property_id}:{period}`, the
cached payload is re-checked against the requesting tenant before it is
returned, and a Redis outage degrades to a live database read instead of a
stale one.

Two related holes closed at the same time:

- `dashboard.py` resolved the tenant as
  `getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"` —
  any user whose tenant failed to resolve was silently dropped into one shared
  bucket with everyone else. There is now no default: no tenant means `403`.
- Revenue was returned for **any** property ID the caller asked for, with no
  ownership check. `GET /dashboard/summary?property_id=prop-004` as Sunset
  returned Ocean's property. The query is now scoped by `(id, tenant_id)` and
  a property belonging to another tenant returns `404` — the same response as
  one that does not exist, so the endpoint cannot be used to enumerate other
  clients' portfolios.
- The frontend sent an `X-Simulated-Tenant` header taken from a component prop.
  The backend ignored it, but a client-supplied tenant has no business being on
  a request at all; it is gone. Tenant comes from the JWT, server-side, only.

---

## Bug 2 — Sunset's March total didn't match their records (timezone)

**Root cause** — [`backend/app/services/reservations.py`](backend/app/services/reservations.py):

```python
start_date = datetime(year, month, 1)          # naive, implicitly UTC
end_date   = datetime(year, month + 1, 1)
```

`check_in_date` is `TIMESTAMP WITH TIME ZONE`, and Sunset's properties are in
`Europe/Paris`. Comparing against naive UTC midnight shifts every property's
month by its UTC offset.

Reservation `res-tz-1` checks in at **2024-02-29 23:30 UTC — which is 00:30 on
1 March in Paris**, where the building is. It is a March booking by any
reasonable definition, and by Sunset's own records. The UTC bounds pushed it
into February:

| | bookings | March total |
|---|---|---|
| naive UTC bounds (before) | 3 | 1000.00 |
| Paris-local bounds (after) | 4 | **2250.00** |

That 1250.00 gap is the discrepancy the client called about.

**Fix:** `month_bounds_utc()` builds the month boundaries in the property's own
IANA timezone (read from `properties.timezone`) and converts them to UTC for the
comparison. DST is handled by `pytz` localisation, so March 2024 in Paris
correctly starts at UTC+1 and ends at UTC+2. The response now reports the
`timezone` and `period` it used, and the UI states it under the figure.

The endpoint gained optional `month` / `year` parameters (all-time remains the
default) so a monthly figure can be requested at all — `calculate_monthly_revenue`
was previously dead code returning `Decimal('0')`.

---

## Bug 3 — Totals off by a few cents (precision)

Amounts are stored as `NUMERIC(10,3)`; three of prop-001's bookings are
333.333 + 333.333 + 333.334, which is exactly 1000.000. Two places threw that
exactness away:

```python
total_revenue_float = float(revenue_data['total'])    # dashboard.py
```
```ts
const displayTotal = Math.round(data.total_revenue * 100) / 100;  // RevenueSummary.tsx
```

Money went `Decimal → float → JSON number → JS double → round`. Halfway values
are not representable in binary, so they round the wrong way: `333.335` becomes
`333.33` rather than `333.34`, once per property per period.

**Fix:** the sum stays in `NUMERIC` in the database and becomes a `Decimal` in
Python (built from `str`, never from a float). It is rounded **once**, at the
API edge, with `ROUND_HALF_UP`, and transported as a **string** so it never
enters a JS double. The response carries both `total_revenue` ("2250.00", for
display) and `total_revenue_exact` ("2250.000", for reconciliation). The UI
formats the string digits directly.

A currency guard came with it: the summation now refuses to add reservations in
different currencies (`409`) rather than silently treating EUR as USD.

---

## Also fixed

- **The property dropdown was hardcoded with all five properties**, so each
  client saw the other's portfolio names and could request revenue they had no
  right to. It is now `GET /dashboard/properties`, scoped to the caller's tenant.
- **`SecureAPI.getTenantId()` never found the tenant** (it read `user_metadata`
  and the root claim, but the login endpoint puts it in `app_metadata`), and on
  an unrecognised ID format it *deleted the caller's access token* — a
  formatting rule that could log people out. It now reads all three locations,
  accepts slug tenants as well as UUIDs, and never destroys a working session.
- **A stale-response race in `RevenueSummary`**: switching properties quickly
  could let a slower earlier request land last and display the wrong property's
  revenue. The effect now ignores responses from a superseded request.
- **The hardcoded "+12%" trend badge** ("fake trend indicator for premium feel")
  is gone. Invented growth figures do not belong on a client revenue dashboard.

---

## Verification

`./scripts/verify_fixes.sh` — 19 checks against the running stack: both clients'
totals match the database, neither can read the other's properties, March
includes the timezone-boundary booking, February is empty, sub-cent sums land on
1000.000, and each client's property list contains only its own.

`backend/tests/test_revenue_fixes.py` — 17 unit tests over the pure logic:
timezone boundaries (including DST and the December rollover), tenant-scoped
cache keys, and the rounding rules, each asserting the old behaviour would fail.
