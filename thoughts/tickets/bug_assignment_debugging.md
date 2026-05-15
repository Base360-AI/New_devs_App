---
type: bug
priority: high
created: 2026-05-15T00:00:00Z
status: reviewed
tags: [assignment, debugging, revenue, privacy, multi-tenant, caching, timezone, finance, frontend, backend]
keywords: [ASSIGNMENT.md, revenue dashboard, Sunset Properties, Ocean Rentals, multi-tenant, tenant isolation, cache, cache key, revenue calculation, reservation, timezone, March, rounding, cents, currency, property, frontend dashboard, backend API, OpenAPI, docker compose]
patterns: [tenant isolation, authorization checks, cache key design, cache invalidation, revenue aggregation, decimal arithmetic, timezone boundaries, month filtering, frontend stale state, API endpoint validation, seed data consistency, performance-sensitive queries]
---

# BUG-001: Investigate and fix assignment revenue dashboard bugs

## Description
Investigate and fix all bugs discoverable in the Property Revenue Dashboard assignment. The known client reports involve incorrect revenue totals for March, possible cross-tenant revenue exposure after refresh, and small financial discrepancies of a few cents. The work should also include other intentional or obvious bugs found in the codebase, especially bugs that affect correctness, privacy, security, reliability, or assignment verification.

This is a single high-priority debugging ticket covering backend services, frontend dashboard behavior, API endpoints, caching, database or seed-data inconsistencies, Docker/config issues if needed, and small targeted tests when they are the fastest way to prove or prevent a regression.

## Context
The assignment describes a recently launched multi-tenant property revenue dashboard. Two major clients reported serious issues:

- Sunset Properties reports that March revenue totals do not match internal records.
- Ocean Rentals reports that refreshing the dashboard can show revenue numbers that appear to belong to another company.
- The finance team noticed totals that are slightly off by a few cents.

The system includes revenue calculations, a caching layer, a frontend dashboard, backend APIs, database schema, and sample data. Client data privacy and financial accuracy are critical. The final deliverable should include a written walkthrough that explains the original behavior, root causes, fixes, verification steps, and advice for presenting the work in a concise interview-style demo.

## Requirements
Find and fix all bugs discovered during the assignment investigation. Fix all issues immediately unless a fix requires a large refactor; stop and discuss before making a major refactor.

### Functional Requirements
- Investigate both provided client accounts:
  - Sunset Properties: `sunset@propertyflow.com` / `client_a_2024`
  - Ocean Rentals: `ocean@propertyflow.com` / `client_b_2024`
- Reproduce and document the before state for each discovered bug when possible.
- Fix incorrect revenue totals, including month-specific issues such as March totals.
- Fix any cross-tenant data leakage or cache contamination between clients.
- Fix rounding, currency, cents, or decimal precision bugs that affect financial totals.
- Fix timezone-related bugs, especially month-boundary behavior for properties in different time zones such as Paris and New York.
- Keep fallback mock data only if it is tenant-aware and clearly logged or flagged as fallback behavior.
- Add explicit `month` and `year` support to dashboard revenue APIs, with the frontend defaulting to March 2024 for the assignment.
- Return financial totals as decimal strings rather than floats.
- Add a tenant-scoped backend properties endpoint and use it to populate the dashboard property selector.
- Show a concise reporting-period label, such as `March 2024, property local time`, so timezone behavior is clear in the UI and walkthrough.
- Fix frontend bugs that affect displayed data, stale state, filters, client switching, refresh behavior, or presentation of correct backend data.
- Fix backend API bugs, including endpoint behavior, authorization checks, data filtering, aggregation logic, and response correctness.
- Inspect backend endpoints directly, not only through the frontend.
- Include test data or seed-data inconsistencies if they cause or mask reported behavior.
- Include performance problems when they affect correctness, privacy, reliability, or realistic assignment behavior.
- Preserve existing structure and patterns where practical; do not rebuild the system.
- Change UI, Docker, config, schema, or seed data only when required to fix or verify a bug.
- Add small targeted tests if they are the fastest way to prove a bug or prevent regression.
- Create a written walkthrough explaining each issue, how it manifested, root cause, fix, verification, and how to present it.

### Non-Functional Requirements
- Treat tenant isolation and privacy as critical requirements.
- Treat financial accuracy as critical; avoid floating-point or rounding behavior that can lose cents.
- Keep fixes minimal and defensible for a take-home assignment.
- Avoid broad polish or redesign work unless it directly supports a bug fix or presentation clarity.
- Do not include accessibility work unless it is itself a functional bug.
- Do not include production hardening unless it affects local assignment behavior or the reported issues.
- Stop for user approval before any large refactor.

## Current State
The assignment reports these symptoms:

- March revenue totals for Sunset Properties do not match expected internal records.
- Ocean Rentals can sometimes see revenue numbers that appear to belong to another company after refreshing.
- Finance sees small totals off by a few cents.
- The repository may contain additional intentional bugs beyond those explicitly mentioned in `ASSIGNMENT.md`.

## Desired State
The dashboard and APIs should return correct, tenant-isolated revenue data for each client across refreshes, direct API calls, property filters, date/month boundaries, and relevant frontend states. Financial totals should use safe precision and rounding. Any discovered correctness, privacy, security, or reliability bugs should be fixed with minimal, understandable changes.

The final walkthrough should let the user present the work clearly by showing the original issue where possible, explaining root cause, showing the fix, and demonstrating verification with the two provided accounts.

## Research Context
Research should begin by reading `ASSIGNMENT.md`, then tracing frontend dashboard data flow, backend revenue endpoints, authentication/authorization, cache implementation, database schema, seed data, reservation models, and date/currency handling.

### Keywords to Search
- `ASSIGNMENT.md` - Source of reported client symptoms and assignment constraints.
- `revenue` - Core calculation and display domain.
- `dashboard` - Frontend surface where users see reported issues.
- `Sunset Properties` - Client A affected by incorrect March totals.
- `Ocean Rentals` - Client B affected by possible cross-tenant data exposure.
- `tenant` / `client` - Multi-tenant isolation and authorization boundaries.
- `cache` / `cacheKey` - Likely area for stale or cross-tenant data bugs.
- `reservation` / `booking` - Source data for revenue aggregation.
- `timezone` / `time_zone` - Month-boundary and property-local date handling.
- `March` - Specific month with reported revenue mismatch.
- `currency` / `amount` / `cents` / `decimal` - Financial precision and rounding bugs.
- `property` - Property filters, ownership, and timezone context.
- `auth` / `authorization` - Endpoint access and tenant restrictions.
- `OpenAPI` / `/docs` - Direct backend endpoint inspection.
- `docker compose` - Local environment setup and verification.

### Patterns to Investigate
- Tenant isolation - Verify every query, cache key, API response, and frontend request is scoped to the authenticated client.
- Authorization checks - Look for endpoints that trust client IDs from requests or omit tenant filters.
- Cache key design - Ensure cache entries include tenant, filters, date range, and any other inputs that affect results.
- Cache invalidation - Check whether stale data persists across refreshes or account changes.
- Revenue aggregation - Verify included reservations, excluded reservations, date filtering, and property ownership.
- Decimal arithmetic - Look for floats used for money and incorrect rounding order.
- Timezone boundaries - Check conversion between UTC, property-local dates, and month filters.
- Frontend stale state - Look for reused cached client data, filters not reset, or stale responses overwriting current state.
- API endpoint validation - Check direct API calls for missing filters, invalid client access, or inconsistent response models.
- Seed data consistency - Verify test/sample data matches tenant relationships, property IDs, dates, time zones, and expected totals.
- Performance-sensitive queries - Look for inefficient patterns that can cause unreliable dashboard behavior or incorrect aggregation under load.

### Key Decisions Made
- This is one high-priority bug ticket, not multiple tickets.
- Scope includes all discoverable assignment bugs and other defensible bugs found in the codebase.
- Scope includes backend, frontend, API docs/endpoints, cache, database/seed data, Docker/config if needed, and small tests when useful.
- Manual verification with both provided client accounts is required.
- Automated tests are optional and should be added only when they are the fastest way to prove or prevent a bug.
- Preserve fallback mock data for demo resilience, but make it tenant-aware and clearly identified as fallback behavior.
- Use explicit dashboard `month` and `year` query parameters, with March 2024 as the frontend default for this assignment.
- Use decimal strings for money values across the dashboard API boundary.
- Fetch tenant-scoped properties from the backend instead of hardcoding all tenant properties in the dashboard.
- Display the reporting period as property-local time in the dashboard.
- Accessibility issues are out of scope unless they are functional bugs.
- Loading, error, and empty states are nice-to-have unless they affect verification, correctness, or user trust around a bug.
- Broad polish and production hardening are out of scope unless assignment-relevant.
- Major refactors require approval before implementation.
- The final Loom itself is out of scope, but a written walkthrough and presentation guidance are required.

## Success Criteria
The ticket is complete when all discovered bugs have been fixed or explicitly escalated because they require a large refactor, and the user has a clear walkthrough for presenting the work.

### Automated Verification
- [ ] Run relevant backend tests if present.
- [ ] Run relevant frontend tests or checks if present.
- [ ] Add and run small targeted tests for bugs where tests are the fastest reliable proof.
- [ ] Run lint/type/build checks if available and practical for changed areas.

### Manual Verification
- [ ] Start the app with `docker compose up --build` or the repository's documented equivalent.
- [ ] Log in as Sunset Properties and verify March revenue totals are correct.
- [ ] Log in as Ocean Rentals and verify no Sunset Properties revenue appears.
- [ ] Refresh both clients' dashboards repeatedly and verify no cross-tenant data appears.
- [ ] Switch between clients in separate sessions or fresh browser contexts and verify data remains isolated.
- [ ] Query backend endpoints directly for both clients and verify tenant-scoped responses.
- [ ] Verify the dashboard property selector only shows properties for the authenticated tenant.
- [ ] Verify `/dashboard/summary` accepts explicit `month` and `year` parameters and defaults from the frontend to March 2024.
- [ ] Verify month-boundary behavior for properties in different time zones, including Paris and New York where data exists.
- [ ] Verify financial totals preserve cents and use correct rounding.
- [ ] Verify financial totals are returned as decimal strings and displayed correctly.
- [ ] Verify fallback mock data, if used, is tenant-aware and clearly identifiable as fallback data.
- [ ] Verify frontend totals, filters, labels, and displayed values match backend data.
- [ ] Verify the dashboard shows the reporting period as property-local time.
- [ ] Verify cache behavior does not leak, reuse, or stale-return another client's data.

## Related Information
- Assignment file: `ASSIGNMENT.md`
- Frontend URL: `http://localhost:3000`
- Backend API docs: `http://localhost:8000/docs`
- Environment command: `docker compose up --build`

## Notes
- Capture before/after evidence where possible so the final explanation can show how each bug manifested and how the fix changed behavior.
- Written walkthrough should include: symptom, impact, reproduction, root cause, fix, verification, and concise presentation advice.
- Recommended presentation structure for a 5-10 minute demo:
  - Start with the three reported risks: wrong totals, tenant leakage, and cents-level accuracy.
  - Show the original broken behavior or describe it with concrete evidence.
  - Explain each root cause in plain language before showing code.
  - Show the minimal fix and why it is safe.
  - Demonstrate verification with both accounts and direct API checks.
  - End by noting any tests added and any intentionally deferred major refactors, if applicable.
