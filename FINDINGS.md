# Revenue dashboard debugging findings

## Bugs and fixes

- **Cross-client cache leakage:** the original Redis key included only property ID, but both clients own `prop-001`. Cache keys now include tenant, property, year, and month, use unambiguous JSON encoding, and carry a new version to avoid old results. Tenant identity comes from authentication; simulation headers cannot select another tenant. Unknown identities no longer default to tenant A, and the dashboard rejects missing tenant membership.
- **Incorrect monthly boundaries:** the original monthly function was a placeholder and the summary aggregated all dates. Existing local edits added March filtering, but fixed the period to March 2024. Requests now accept a validated month/year. PostgreSQL converts each local month boundary using the property's IANA timezone. The interval includes the start and excludes the next month's start, including across daylight-saving changes.
- **Broken database access hidden by plausible totals:** the pool referenced missing Supabase settings, used a synchronous pool with an async engine, and returned a coroutine where callers expected a session context manager. It now uses DATABASE_URL, SQLAlchemy's async pool, and a reusable shared pool. Failed revenue queries return HTTP 503 rather than fabricated or zero totals. Redis failures fall back to the real database.
- **Financial precision:** SQL NUMERIC aggregation stays decimal through the API and UI. No conversion to Python float or JavaScript Number and no per-reservation cent rounding. The UI preserves all three source decimal places. Different currencies are reported separately rather than incorrectly added as USD; empty months do not invent a currency.
- **Misleading dashboard:** the original static selector exposed other clients' property names and assigned the wrong name to Ocean's shared ID. It now loads the authenticated tenant's properties. The invented 12% growth badge is removed. Reporting month is explicit, and obsolete asynchronous responses are ignored when selection changes.

The four files already edited before this debugging session were reviewed and built upon, including the tenant cache key and decimal-string changes.

## Verified seeded March 2024 results

| Client | Property | Exact total | Reservations |
| --- | --- | --- | --- |
| Sunset | prop-001 | USD 2250.000 | 4 |
| Sunset | prop-002 | USD 4975.500 | 4 |
| Sunset | prop-003 | USD 6100.500 | 2 |
| Ocean | prop-001 | No reservations | 0 |
| Ocean | prop-004 | USD 1776.500 | 4 |
| Ocean | prop-005 | USD 3256.000 | 3 |

Ocean's prop-001 deliberately has no reservations in the supplied seed. Do not add invented bookings to make it show a nonzero result.

The Sunset boundary reservation checks in at 2024-02-29 23:30 UTC, which is March 1 at 00:30 in Paris. Its USD 1250 belongs in March. The three fractional amounts 333.333 + 333.333 + 333.334 sum exactly to 1000.000.

## Validation

Run from the repository root with Docker services running:

```sh
docker compose exec -T backend python -m unittest discover -s tests -v
docker compose build frontend
docker compose up -d --no-deps frontend
```

The tests use actual PostgreSQL queries with temporary fixture changes inside rolled-back transactions. They cover Paris/New York month edges and DST, December rollover, empty months, fractional amounts, mixed currencies, foreign-property rejection, tenant/month cache isolation, cache outages, database failure responses, missing tenant identity, real login credentials, warm API responses, and invalid month input.

Browser checks completed: Sunset login, March 2250.000/four bookings, February empty, logout, Ocean login, Ocean-only property names, Lakeside Cottage 1776.500/four bookings. Frontend production build passed in Docker. The host npm command could not run because the checked-in node_modules lacks the Vite executable; Docker supplies a working build environment.

## Loom outline (about 6 minutes)

1. **0:00-0:45 — Explain the reports.** Open ASSIGNMENT.md. Describe the three symptoms: incorrect months, cross-client results, and rounding.
2. **0:45-2:00 — Show isolation.** Open cache.py and the tenant checks in dashboard.py. Explain why property ID alone is unsafe. Log in as Sunset and Ocean in turn; show the different property lists and prop-001 results.
3. **2:00-3:15 — Explain the calendar bug.** Open reservations.py and the boundary seed row. Explain Paris midnight and the half-open interval. Show March versus February in the dashboard.
4. **3:15-4:15 — Explain precision.** Show the three fractional seed values and the exact decimal-string response. Explain that currencies remain separate and no rounding policy was silently invented.
5. **4:15-5:15 — Explain the hidden failure.** Open database_pool.py. Describe missing settings, the incorrect async session API, and why fake totals or zero on errors are dangerous. Show the HTTP 503 handling.
6. **5:15-6:00 — Demonstrate regression checks.** Run the unittest command above, show the passing result, and briefly describe DST boundaries, isolation, and outage checks.

The Loom recording itself has not been created. Record the walkthrough with your own narration before submitting. This is a focused assignment fix, not a production security audit of the repository's mock authentication system.
