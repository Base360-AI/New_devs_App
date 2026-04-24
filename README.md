# PropertyOS — Debugging Investigation

A multi-tenant property revenue dashboard handed over with a vague complaint:
*"two clients say the numbers are wrong, and one of them is seeing data that
doesn't belong to them."* This repo is the investigation that followed —
14 bugs found and fixed across the stack, from a cross-tenant cache leak to
float drift on money to an nginx config that silently returned HTML for every
API call in Docker.

Not a from-scratch build. A debugging exercise against an existing FastAPI +
React + Postgres + Redis codebase, with all fix rationale, postmortems, and
regression tests kept in-repo so the reasoning is legible without me in the
room.

## The through-line

> Every layer had the right infrastructure. The pieces were never wired
> together.

Row-level security policies existed — but the backend connected as a
superuser, so they did nothing. A timezone-aware monthly revenue function
existed — but no endpoint called it. A secure client wrapper with
tenant-scoped queries existed — but the dashboard bypassed it. An IndexedDB
logout cleaner existed — but the logout path never called it. The bugs
weren't missing features. They were missing wires.

That pattern shaped every fix: before writing new code, find the correct code
that's already there and connect it.

## The 14 bugs

Grouped by what the user would have lived through.

### Trust (data isolation)

| # | Bug | Severity |
|---|---|---|
| 1 | Cross-tenant cache poisoning — cache key missing `tenant_id` | P0 |
| 5 | Property dropdown showed every client's properties | P0 |
| 8 | Unknown email silently granted full access to Tenant A | P0 |
| 10 | Revenue summary defaulted to `prop-001` before any selection | Medium |
| 11 | `window.debugAuth` exposed full JWT to any script on the page | High |
| 14 | Emails and JWT fragments logged to Sentry/Datadog | High |

### Accuracy (financial correctness)

| # | Bug | Severity |
|---|---|---|
| 2 | Monthly revenue used naive UTC instead of property timezone | High |
| 3 | `float()` on money caused cent drift and `NaN` renders | Medium |
| 9 | Hardcoded `+12%` growth badge rendered for every tenant | High |

### Infrastructure (the system wasn't running correctly)

| # | Bug | Severity |
|---|---|---|
| 4 | nginx missing `/api/` proxy — every API call returned HTML | P0 |
| 6 | `QueuePool` passed to async engine — 503 on every request | High |
| 7 | Supabase `.single()` returned list — 500 on every dashboard load | High |
| 12 | Fresh Docker containers started without RLS policies | High |
| 13 | Two independent Redis connection pools under load | Medium |

Each bug has a full postmortem in [POSTMORTEM.md](POSTMORTEM.md) — impact,
cause, why it wasn't caught, fix, and what prevents recurrence — and a
working-notes entry in [NOTES.md](NOTES.md) with root cause, regression test
reference, and what I'd watch for next.

## What's in the repo

- **[NOTES.md](NOTES.md)** — engineer's working notes for each bug and the
  architectural hardening that followed (typed tenant identifiers, single
  mandatory tenant dependency, cache key centralisation, RLS session wiring,
  structured logging, mypy --strict gate, convention tests). Plus an
  out-of-scope table of findings deferred deliberately, and a prioritised
  "if I had one more week" list.
- **[POSTMORTEM.md](POSTMORTEM.md)** — one incident write-up per bug in the
  voice I'd use internally: impact first, technical cause second, explicit
  answer to *why didn't we catch this*.
- **`backend/tests/`** — 89 passing tests. Unit, integration, contract
  (schemathesis), and convention tests (CI lints that grep `app/` for
  `float(revenue)`, `datetime.utcnow()`, inline cache keys, missing
  `require_tenant_scope`).
- **`frontend/e2e/`** — Playwright suite with a shared-browser tenant-switch
  test: log in as A, log out, log in as B, assert zero A-data survives in
  DOM, localStorage, sessionStorage, or network response bodies.
- **`database/migrations/`** — RLS policies and an `app_user` role with
  `NOSUPERUSER, NOINHERIT` so RLS becomes a real backstop instead of a
  false safety net.

## The Claude Code setup

The whole investigation was run inside Claude Code with a deliberate
configuration for this kind of work:

- **[CLAUDE.md](CLAUDE.md)** — stop rules (`float()` on money,
  superuser-bypassing-RLS, silencing linters to make violations go away),
  naming conventions, test credentials, pointers to auth and context files.
- **`.claude/agents/`** — purpose-built subagents:
  `security-reviewer`, `context-auditor`, `test-writer`, `explore-agent`,
  `cto-interviewer`. Each has a narrow brief and read-only or
  narrowly-scoped tool access.
- **`.claude/commands/`** — slash commands for the workflow I actually used:
  `/bug-fix-start`, `/pre-fix-check`, `/fix-plan`, `/root-cause-analysis`,
  `/ai-code-review`, `/context-audit`, `/notes-update`, `/session-end`.
- **`.claude/context-snapshot.md`** — re-read after compaction so long
  sessions don't lose the architectural picture.

The point of the setup isn't agent novelty. It's that the investigation
produced the same artifacts a human-run one would — postmortems, regression
tests, an honest out-of-scope list — because the workflow forced them at
each step.

## Running it

```bash
docker-compose up
# Frontend: http://localhost:3000
# API:      http://localhost:8000/docs
```

Test credentials (both tenants share `prop-001` by design — that's what
demonstrates the cache poisoning bug):

- Tenant A: `tenant-a@example.com` / `client_a_2024`
- Tenant B: `tenant-b@example.com` / `client_b_2024`

Tests:

```bash
cd backend && python -m pytest        # 89 passed
cd frontend && npx playwright test    # E2E tenant-isolation suite
```

## Walkthrough

A Loom walkthrough of the investigation and the fixes is linked separately —
reach out if you'd like the URL.
