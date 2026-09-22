# Revenue regressions

Run from the repository root after `docker compose up --build -d`:

```sh
docker compose exec -T -e RUN_REVENUE_INTEGRATION=1 backend python -B -m unittest discover -s tests -v
```

Without `RUN_REVENUE_INTEGRATION=1`, PostgreSQL/live API tests are skipped. No additional test dependencies are required.

- `test_revenue.py`: cache tenant/period isolation, legacy and mismatched entries, failure behavior, UTC/DST boundaries, async pool lifecycle, API validation, decimal-string contract and ROUND_HALF_UP.
- `test_revenue_integration.py`: real PostgreSQL queries using rollback-only fixtures, exact month endpoints, precision through the API/cache, both assignment logins, seed totals, ownership checks and actual Redis payloads.
- Database fixture tests roll back their writes; live assignment tests only read seeded business data and populate normal expiring revenue cache entries.

The summary endpoint requires `property_id`, `month` (1–12), and `year` (1–9998). `total_revenue` is now a two-decimal string, rounded HALF_UP once after summing NUMERIC amounts. Revenue is attributed by check-in date in the property's timezone; the upper month boundary is exclusive. The UI displays the returned string without float conversion. No currency conversion is performed; mixed-currency totals are rejected.

Loom: show `cache.revenue_cache_key`, `DatabasePool.initialize/get_session`, `reservations.monthly_utc_bounds/calculate_monthly_revenue`, `dashboard.get_dashboard_summary`, and the month input/string rendering in `Dashboard.tsx` / `RevenueSummary.tsx`. Demonstrate March vs April, both tenants' shared `prop-001`, a foreign-property 404, and the integration test results.
