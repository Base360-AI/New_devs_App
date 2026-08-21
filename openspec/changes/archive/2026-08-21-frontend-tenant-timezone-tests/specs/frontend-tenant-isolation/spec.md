## Purpose

Keeps Sunset Properties and Ocean Rentals revenue data apart in the dashboard UI, API client, and browser caches so a refresh cannot show another company's totals.

## ADDED Requirements

### Requirement: Revenue requests use the authenticated tenant
The dashboard MUST request revenue using the signed-in user's tenant identity. It MUST NOT send a hardcoded simulated tenant when a real session tenant is available.

#### Scenario: Sunset user loads the default property
- **WHEN** a tenant-a user opens the revenue dashboard
- **THEN** the revenue request identifies tenant-a
- **AND** the displayed total matches tenant-a's records for that property

#### Scenario: Ocean user loads the same property id
- **WHEN** a tenant-b user opens the revenue dashboard for property id prop-001
- **THEN** the request identifies tenant-b
- **AND** the UI MUST NOT show tenant-a's Beach House Alpha totals

#### Scenario: No simulated-tenant override on a real session
- **WHEN** a signed-in user loads revenue without an explicit debug override
- **THEN** the client MUST NOT attach a default simulated-tenant value of candidate

### Requirement: Client caches are tenant-scoped
Browser and in-memory caches for revenue and dashboard payloads MUST include tenant identity in the cache key. A cache hit for tenant A MUST be unreachable when tenant B is active.

#### Scenario: Refresh after switching companies
- **WHEN** tenant-a revenue for prop-001 is cached in the browser
- **AND** the session switches to tenant-b
- **THEN** a refresh MUST NOT render tenant-a's cached total

#### Scenario: Concurrent tabs with a shared property id
- **WHEN** tenant-a and tenant-b both cache revenue for prop-001
- **THEN** two distinct cache entries MUST exist
- **AND** each tab MUST show only its own tenant's total

### Requirement: Frontend tests lock isolation
The project MUST include automated frontend tests that fail if tenant identity is omitted from revenue requests or client cache keys.

#### Scenario: Isolation suite exists
- **WHEN** the frontend test suite runs
- **THEN** scenarios covering tenant-a vs tenant-b revenue isolation MUST execute
- **AND** they MUST fail if the client reuses an unscoped cache key or a hardcoded candidate tenant
