# PropertyOS — Multi-tenant rental ops platform

**Stack:** FastAPI + React + PostgreSQL + Redis + Docker

## Commands
- Start: `docker-compose up`
- Test: `cd backend && python -m pytest`
- Lint backend: `cd backend && ruff check .`
- Lint frontend: `cd frontend && npx eslint .`
- Type-check frontend: `cd frontend && npx tsc --noEmit`

## Architecture
- `frontend/src/` — React + TS components
- `backend/app/services/` — business logic (cache, reservations)
- `backend/app/core/` — infra: db pool, cache config, auth
- `backend/app/api/v1/` — FastAPI endpoints
- `database/` — migrations + seed data

## Bugs to fix
- Bug-1 (cache poisoning): `@backend/app/services/cache.py` — cache key missing tenant_id
- Bug-2 (timezone): `@backend/app/services/reservations.py` — UTC used instead of property timezone
- Bug-3-backend (precision): `@backend/app/api/v1/dashboard.py` — float() on money calculations
- Bug-3-frontend (type): `@frontend/src/components/Dashboard.tsx` — string revenue type not handled

## Stop rules
- Never touch auth without reading `backend/app/core/secure_client.py` first
- Never fix cache without confirming `tenant_id` is in scope for the key
- Never modify `.ruff.toml`, `eslint.config.js`, or `pyproject.toml` to silence violations — fix the code
- Never return unfiltered query results from `secure_client.py` — raise ValueError on unknown tables
- Never use `float()` for monetary calculations — use `Decimal.quantize(TWOPLACES, ROUND_HALF_UP)`
- Never use hardcoded tokens or credential fallbacks in any environment

## Naming conventions
- Files: kebab-case
- Components: PascalCase
- Errors: typed only — `NotFoundError`, `TenantError` — never bare `Exception`

## Test credentials
- Tenant A: `tenant-a@example.com` / `client_a_2024`
- Tenant B: `tenant-b@example.com` / `client_b_2024`
- Both tenants share `prop-001` by design — demonstrates cache poisoning bug

## References
- Fix rationale: `@NOTES.md` — read before any backend change
- Auth: `@backend/app/core/secure_client.py` — read before touching auth or data access paths
- Context snapshot: `@.claude/context-snapshot.md` — re-read if context was lost after compaction
