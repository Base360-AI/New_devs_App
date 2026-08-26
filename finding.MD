# Property Revenue Dashboard — Findings and Fixes

## Executive summary

The investigation identified three primary production issues:

1. Sunset Properties received incorrect March revenue because the application was not reading the real database successfully and monthly reservations were not explicitly bucketed in the property's timezone.
2. Ocean Rentals could receive Sunset's cached revenue because the Redis key contained only the property ID, even though property IDs are unique only within a tenant.
3. Revenue was converted from PostgreSQL `NUMERIC` to a floating-point number and rounded again in the frontend, creating a risk of cent-level inaccuracies.

The changes preserve the existing FastAPI, PostgreSQL, Redis, and React architecture. They correct the database connection, calculate local-calendar monthly revenue, isolate cached data by tenant and period, preserve decimal precision, and remove unsafe tenant fallbacks.

## Finding 1: the revenue service returned mock data

### Evidence

The database contains four March reservations for Sunset's `prop-001`, totalling `2250.000`. The service returned `1000.00` and three reservations.

The database pool attempted to build its connection URL from `supabase_db_*` settings that do not exist. Initialization failed with:

```text
Settings object has no attribute 'supabase_db_user'
```

The revenue service caught that failure and returned hard-coded property data. This made an unavailable database look like a successful financial response.

### Fix

- Build the SQLAlchemy async connection from the configured `DATABASE_URL`.
- Use the `postgresql+asyncpg` driver.
- Share one pool per backend process.
- Remove the fabricated financial fallback.
- Propagate database failures instead of returning believable but incorrect values.

Financial systems should fail visibly when their source of truth is unavailable.

## Finding 2: March was not defined in the property's timezone

Sunset's `prop-001` is in `Europe/Paris`. Its boundary reservation checks in at:

```text
2024-02-29 23:30 UTC
```

In Paris, that timestamp is:

```text
2024-03-01 00:30 Europe/Paris
```

It therefore belongs to March for that property.

### Correct March calculation

- Boundary reservation: `1250.000`
- Three additional reservations: `333.333 + 333.333 + 333.334 = 1000.000`
- Correct total: `2250.000`
- Correct reservation count: `4`

### Fix

The active revenue query now:

- Joins the property to obtain its IANA timezone.
- Converts each `TIMESTAMP WITH TIME ZONE` using `AT TIME ZONE properties.timezone`.
- Uses a half-open interval: `month_start <= check_in < next_month_start`.
- Accepts explicit `month` and `year` parameters.

The frontend now sends the selected reporting month and year, making the period shown by the monthly dashboard explicit.

## Finding 3: Redis cache keys were not tenant-safe

### Root cause

The original key was:

```text
revenue:{property_id}
```

Both Sunset and Ocean own a different `prop-001`. If Sunset populated the key first, Ocean received Sunset's cached object before the tenant-filtered database query executed.

The `_t` query parameter added by the frontend did not bypass Redis because it was not part of the server-side cache key.

### Fix

The key now includes every dimension that changes the result:

```text
revenue:{tenant_id}:{property_id}:{year}:{month}
```

The cache also validates the tenant, month, and year stored in the cached payload before returning it.

## Finding 4: `default_tenant` failed open

The dashboard previously converted an absent tenant assignment into `default_tenant`. A multi-tenant financial endpoint should never invent an authorization boundary.

### Fix

- Authentication returns a typed `AuthenticatedUser`.
- A user without `tenant_id` receives HTTP 403.
- Revenue is never queried or cached under a placeholder tenant.
- Unknown users no longer default to `tenant-a`.
- Foreign and nonexistent property IDs both return the same generic HTTP 404, preventing property-enumeration leaks.

Tenant claims are read from signed, server-controlled `app_metadata`, not user-editable `user_metadata`.

## Finding 5: money crossed the API as a float

PostgreSQL stores reservation amounts as `NUMERIC(10,3)`, which is exact. The old endpoint converted the aggregate with `float()`, and React rounded it again with `Math.round`.

Binary floating-point cannot exactly represent many decimal fractions. Repeated conversion and rounding can therefore produce incorrect cents.

### Fix

- Keep values as PostgreSQL `NUMERIC` while aggregating.
- Sum first and round once to two decimal places in SQL.
- Serialize the final amount as a string such as `"2250.00"`.
- Format that string for display without converting it to a JavaScript `Number`.

The frontend `formatMoney` helper only adds thousands separators and guarantees two displayed decimal digits:

```text
"2250.00"  -> "2,250.00"
"-1234.5"  -> "-1,234.50"
```

## Finding 6: the property selector exposed every tenant's properties

The original React dashboard contained one hard-coded list with properties belonging to both clients. Every user saw the same options.

### Fix

`GET /api/v1/dashboard/properties` now:

1. Uses the authenticated user's tenant.
2. Queries `properties` with `WHERE tenant_id = :tenant_id`.
3. Returns only `id`, `name`, and `timezone`.

The frontend selector is populated from this endpoint. Sunset sees only Sunset properties, and Ocean sees only Ocean properties.

The fabricated 12% trend badge was also removed because it was not backed by data.

## API behavior after the fixes

### Monthly summary

```http
GET /api/v1/dashboard/summary?property_id=prop-001&month=3&year=2024
```

Sunset response:

```json
{
  "property_id": "prop-001",
  "month": 3,
  "year": 2024,
  "total_revenue": "2250.00",
  "currency": "USD",
  "reservations_count": 4
}
```

Ocean's separate `prop-001` returns `"0.00"` for the same period.

### Tenant properties

```http
GET /api/v1/dashboard/properties
```

The response contains only properties belonging to the authenticated tenant.

## Verification performed

- Ran the backend unit and regression test suite.
- Verified the timezone-aware monthly query.
- Verified exact decimal string output.
- Verified tenant- and period-scoped cache keys.
- Verified a missing tenant is rejected.
- Verified an unknown or foreign property returns 404.
- Built the frontend successfully.
- Logged in through the live API with both supplied client accounts.
- Confirmed Sunset March `prop-001` returns `"2250.00"` and four reservations.
- Confirmed Sunset February `prop-001` returns `"0.00"`, proving the timezone-boundary reservation is assigned to March.
- Confirmed Ocean `prop-001` remains `"0.00"` after Sunset has populated its own cache.
- Confirmed each account receives only its own property list.

## Conclusion

The corrected dashboard now reads revenue from the actual database, assigns reservations to calendar months using each property's timezone, preserves decimal precision, and isolates both cached revenue and property metadata by tenant.

For the supplied dataset:

- Sunset `prop-001`, March 2024: `USD 2250.00`, four reservations.
- Sunset `prop-001`, February 2024: `USD 0.00`.
- Ocean `prop-001`, March 2024: `USD 0.00`.

Repeated requests from either client return only that client's results.
