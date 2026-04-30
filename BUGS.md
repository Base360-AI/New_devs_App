# Bug Report — Property Revenue Dashboard

**Reporter:** Daan Barsukoff Poniatowsky
**Status:** All bugs resolved; fixes ready for review
**Reported issues addressed:** Client A (revenue mismatch), Client B (cross-tenant data appearing in their account), Finance (cents off)

Bugs are listed in the same order as the fixes in `FIXES.md`. Each entry follows the same format: symptom, impact, root cause, fix, verification, files.

---

## BUG-001 — Database query path returns fabricated data instead of real numbers

| Field | Value |
|---|---|
| **Severity** | Critical (data accuracy) |
| **Reported by** | Client A (Sunset Properties), via CEO |
| **Status** | Fixed |

### Symptom

Beach House Alpha (`prop-001`, tenant-a) showed $1,000.00 with 3 reservations on the dashboard. The seed data shows four reservations totaling $2,250.00. One reservation (`res-tz-1`, $1,250.00) was missing from the displayed total.

### Impact

Sunset Properties' board pack would have been off by $1,250 for one property. The same pattern affected any tenant whose true revenue diverged from a hard-coded mock dictionary embedded in the backend code.

### Root cause

A three-layer cascade in `backend/app/core/database_pool.py`:

1. The connection-string template referenced `Settings` attributes that don't exist (`supabase_db_user`, `supabase_db_password`, etc.). Accessing them raised `AttributeError`.
2. After fixing #1, `poolclass=QueuePool` was incompatible with `create_async_engine`.
3. After fixing #2, `async def get_session()` returned a coroutine when callers expected an async-context-manager.

The cascade caused `DatabasePool().initialize()` to silently fail. `services/reservations.py::calculate_total_revenue` had a broad `except Exception` block that returned hard-coded mock data — and the mock dict was keyed only on `property_id`, ignoring `tenant_id`.

### Fix

In `database_pool.py`: use `settings.database_url` (the actual configured value); drop the incompatible `QueuePool`; change `get_session()` from `async def` to plain `def`.

In `reservations.py`: remove the mock-data dict and the broad exception handler. Let real DB errors propagate to the API layer, which now returns 5xx and the UI shows "Failed to load revenue data" — the system fails closed rather than fabricating revenue.

### Verification

`SELECT SUM(total_amount), COUNT(*) FROM reservations WHERE property_id='prop-001' AND tenant_id='tenant-a'` returns `2250.000 / 4`. The dashboard now matches.

### Files changed

- `backend/app/core/database_pool.py`
- `backend/app/services/reservations.py`

### Notable

The mock dict's values matched the real seed totals for *four of five* properties. Only `prop-001 / tenant-a` differed — by exactly the value of the timezone-test reservation. That's the breadcrumb that made this bug findable; without it, the dashboard would have looked plausible end-to-end.

---

## BUG-002 — Cross-tenant revenue data leak via cache

| Field | Value |
|---|---|
| **Severity** | Critical (privacy / data confidentiality) |
| **Reported by** | Client B (Ocean Rentals), via CEO |
| **Status** | Fixed |

### Symptom

When tenant-a queried any property's revenue, the result was cached. For the next 5 minutes, any other tenant querying the same `property_id` received tenant-a's numbers — even though the underlying SQL filter was tenant-correct. Both tenants own a property called `prop-001`, so this collision was guaranteed in normal usage.

### Impact

A property manager logged in as Ocean Rentals could see Sunset Properties' revenue numbers under their own dashboard. Direct violation of multi-tenant isolation.

### Root cause

`backend/app/services/cache.py:13` —

```python
cache_key = f"revenue:{property_id}"
```

The Redis cache key contained only `property_id`. Both tenants own a `prop-001` (the schema's composite primary key `(id, tenant_id)` allows it), so cache entries collided.

### Fix

Tenant-scoped the key:

```python
cache_key = f"revenue:{tenant_id}:{property_id}"
```

### Verification

Flush Redis. Login as tenant-a, hit `/dashboard/summary?property_id=prop-001` (returns $2,250.00 / 4). Login as tenant-b, hit the same URL. Pre-fix: tenant-b sees $2,250.00 / 4 (tenant-a's data). Post-fix: tenant-b sees $0.00 / 0 (their actual data). Redis now stores two independent keys: `revenue:tenant-a:prop-001` and `revenue:tenant-b:prop-001`.

### Files changed

- `backend/app/services/cache.py`

---

## BUG-003 — Property dropdown is hardcoded for tenant-a, mislabels tenant-b's properties

| Field | Value |
|---|---|
| **Severity** | High (privacy / UX) |
| **Reported by** | Client B, indirectly ("we see numbers that look like they belong to another company") |
| **Status** | Fixed |

### Symptom

The dashboard's property selector showed five entries with tenant-a's names regardless of who was logged in. `ocean@propertyflow.com` saw "Beach House Alpha" in the dropdown — but tenant-b's `prop-001` is actually "Mountain Lodge Beta" in New York. Each tenant also saw two ghost entries that didn't belong to them (returning $0 / 0).

### Impact

This is part of what Client B was complaining about — the labels under which their numbers appeared belonged to a different company. Even when the underlying SQL was tenant-correct, the UI's labels were not.

### Root cause

`frontend/src/components/Dashboard.tsx` defined a static `PROPERTIES` array with five hardcoded entries. The frontend never asked the backend "which properties does this tenant own?"

### Fix

New backend endpoint `GET /api/v1/dashboard/properties` that returns properties filtered by the authenticated user's `tenant_id`. New `SecureAPI.getProperties()` client method. Dashboard component fetches on mount and renders the response, replacing the hardcoded array.

### Verification

Log in as each tenant, open the dropdown.

- Tenant-a: Beach House Alpha (Paris), City Apartment Downtown, Country Villa Estate.
- Tenant-b: Mountain Lodge Beta (NY), Lakeside Cottage, Urban Loft Modern.

No ghost entries; no mislabeling.

### Files changed

- `backend/app/api/v1/dashboard.py`
- `frontend/src/lib/secureApi.ts`
- `frontend/src/components/Dashboard.tsx`

---

## BUG-004 — Revenue totals lose precision in the float cast

| Field | Value |
|---|---|
| **Severity** | Medium (data accuracy) |
| **Reported by** | Finance ("off by a few cents here and there") |
| **Status** | Fixed |

### Symptom

For certain reservation amounts, the displayed total differed from a Decimal-precise calculation by 1¢ to a few cents. Finance noticed but couldn't pinpoint when, because the bug only triggers on values whose binary float representation drifts across a half-cent boundary.

### Impact

Accounting reports diverge from the dashboard. Hard to reconcile; erodes trust in the revenue numbers.

### Root cause

`backend/app/api/v1/dashboard.py` (pre-fix) cast the Decimal-precise value to a Python `float` before sending it over JSON. `float("1.005")` is stored as `1.0049999999999999`. The frontend's `Math.round(value * 100) / 100` then gave `$1.00` instead of the correct `$1.01`. Because the backend already corrupted the value, no frontend fix could recover it.

### Fix

Round in `Decimal` space on the backend before crossing into float, using `ROUND_HALF_UP`:

```python
def _round_to_cents(value: str) -> float:
    return float(Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
```

### Verification

Inserted a single reservation of `$1.005` into `tenant-b/prop-001`. Dashboard displays `$1.01`. Pre-fix would have displayed `$1.00`. All existing seed-data totals unchanged (regression check passed for all six tenant/property combinations).

### Files changed

- `backend/app/api/v1/dashboard.py`

### Open question for Finance

We use `ROUND_HALF_UP`. Some accounting standards mandate `ROUND_HALF_EVEN` (banker's rounding). The two differ on values exactly at the half-cent. Worth a one-line confirmation before this is shipped.

---

## BUG-005 — Monthly revenue function is a stub; uses naive datetimes

| Field | Value |
|---|---|
| **Severity** | Medium (correctness) |
| **Reported by** | Internal audit during fix work |
| **Status** | Fixed |

### Symptom

`services/reservations.py::calculate_monthly_revenue` was wired in name only: it built a SQL query string but never executed it, returning `Decimal('0')` as a placeholder. The date boundaries it constructed (`datetime(year, month, 1)`) were timezone-naive, so any future use against the `TIMESTAMP WITH TIME ZONE` columns would have produced results dependent on the database session timezone — non-deterministic across environments.

### Impact

Today: no impact, because no endpoint called the function. Latent: any future "monthly revenue" feature would have produced inconsistent results across UTC, Paris, and New York time depending on the session timezone of whichever Postgres replica answered. The seed data deliberately includes `res-tz-1` (Feb 29 23:30 UTC = Mar 1 00:30 Paris) to expose this.

### Root cause

A half-finished implementation. The skeleton was there, the SQL was a comment, the boundaries were naive, no caller existed.

### Fix

`calculate_monthly_revenue` now:

- Takes `tenant_id` (previously absent).
- Constructs boundaries as `datetime(year, month, 1, tzinfo=timezone.utc)` — explicitly UTC-anchored, deterministic across environments.
- Actually executes the SQL via the database pool.
- Returns the same Decimal-precise shape as `calculate_total_revenue`.

A new endpoint `GET /api/v1/dashboard/monthly` exposes it (defaulting to March 2024 — the only month the seed covers). The frontend now displays "March 2024 revenue: $X.XX" under the all-time total. The dashboard's existing copy ("Monthly performance insights") finally reflects what's shown.

### Verification

`/dashboard/monthly?property_id=prop-001&month=3&year=2024` for tenant-a returns `$1,000.00 / 3 reservations` — the three "decimal" reservations summing to exactly $1,000. `res-tz-1` is correctly excluded because it falls on Feb 29 in UTC.

### Open design question

UTC-anchored boundaries are deterministic but may not be what Sunset Properties expects — `res-tz-1` is "March" in their (Paris) frame of reference. A future enhancement would compute monthly boundaries in each *property's* local timezone (the `properties.timezone` column already stores it). That's a deliberate next step, not a regression.

### Files changed

- `backend/app/services/reservations.py`
- `backend/app/api/v1/dashboard.py`
- `frontend/src/lib/secureApi.ts`
- `frontend/src/components/RevenueSummary.tsx`

---

## BUG-006 — TenantResolver defaults to a fixed tenant for unknown users

| Field | Value |
|---|---|
| **Severity** | High (latent privacy hole) |
| **Reported by** | Internal audit during fix work |
| **Status** | Fixed |

### Symptom

`TenantResolver.resolve_tenant_id` had a hardcoded email-to-tenant map with a default `return "tenant-a"` for any unrecognized email. Today our two demo users hit explicit branches, so the bug isn't observable in the running app — but the moment a third user is added (or a malicious user obtains a valid token), they silently inherit Sunset Properties' data.

### Impact

Latent. Becomes active the moment user provisioning expands beyond the two demo accounts. Silent privilege escalation, no audit trail.

### Root cause

`backend/app/core/tenant_resolver.py:84-92` (pre-fix):

```python
if user_email == "sunset@propertyflow.com":   return "tenant-a"
if user_email == "ocean@propertyflow.com":    return "tenant-b"
if user_email == "candidate@propertyflow.com": return "tenant-a"
return "tenant-a"   # ← any unknown user inherits tenant-a
```

The same file already contained `resolve_tenant_from_token`, which correctly extracts `tenant_id` from JWT claims — it just wasn't being called by `resolve_tenant_id`. Looks like a half-finished refactor.

### Fix

`resolve_tenant_id` now decodes the JWT (signature already verified upstream), reads `tenant_id` from `app_metadata`/`user_metadata`/top-level claims via `resolve_tenant_from_token`, and returns `None` if no tenant can be derived. The API layer treats `None` as a 400 (see BUG-007).

### Verification

Forge a JWT signed with the dev secret but without `app_metadata.tenant_id`. Hit any dashboard endpoint. Returns HTTP 400 `"No tenant context for user"` instead of silently returning tenant-a's data.

### Files changed

- `backend/app/core/tenant_resolver.py`

---

## BUG-007 — Dashboard endpoints accept missing tenant context with a silent fallback

| Field | Value |
|---|---|
| **Severity** | High (latent privacy hole) |
| **Reported by** | Internal audit during fix work |
| **Status** | Fixed |

### Symptom

`/dashboard/summary` had:

```python
tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"
```

If a request reached this endpoint without a tenant context, the SQL ran against `tenant_id = "default_tenant"` instead of the request being refused. Today no rows match that string, so `$0 / 0` is returned — but if a fixture, migration, or test ever inserts data with `tenant_id = 'default_tenant'`, every tenant-less request gets it.

### Impact

Latent privacy hole; inconsistent contract across endpoints (the new `/dashboard/properties` correctly raises 400 in the same situation).

### Root cause

The `getattr(..., default) or default` pattern silently substitutes a sentinel value for a missing security-critical input.

### Fix

All three dashboard endpoints now use a shared helper that raises:

```python
def _require_tenant(current_user) -> str:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context for user")
    return tenant_id
```

### Verification

Same forged-JWT test as BUG-006; all three dashboard endpoints (`/properties`, `/summary`, `/monthly`) refuse with HTTP 400.

### Files changed

- `backend/app/api/v1/dashboard.py`

---

## Out-of-scope observations

Things noted but not changed in this round:

- **`debugTenant` prop / `X-Simulated-Tenant` header** in the frontend — currently dead (backend ignores the header), but a footgun for future "tenant simulation" debug flows. Recommend cleanup PR.
- **`calculate_total_revenue` instantiates a new `DatabasePool` per call** instead of reusing the module-level singleton. Not a correctness bug; resource-efficiency.
- **Two divergent `ADMIN_EMAILS` lists** in `core/auth.py` and `api/v1/login.py`. Should converge.
- **Significant dead infrastructure code** (token services, persistent sessions, circuit-breaker fallback, Lightning SQL files) wired up but unused by the live flow. Out of scope for this round; flagged for an architecture conversation.
