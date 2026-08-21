Feature: Frontend tenant isolation
  Dashboard and API client keep Sunset and Ocean revenue apart in requests, headers, and browser caches.

  Scenario: Sunset user loads the default property
    When a tenant-a user opens the revenue dashboard
    Then the revenue request identifies tenant-a
    And the displayed total matches tenant-a's records for that property

  Scenario: Ocean user loads the same property id
    When a tenant-b user opens the revenue dashboard for property id prop-001
    Then the request identifies tenant-b
    And the UI must not show tenant-a's Beach House Alpha totals

  Scenario: No simulated-tenant override on a real session
    When a signed-in user loads revenue without an explicit debug override
    Then the client must not attach a default simulated-tenant value of candidate

  Scenario: Refresh after switching companies
    When tenant-a revenue for prop-001 is cached in the browser
    And the session switches to tenant-b
    Then a refresh must not render tenant-a's cached total

  Scenario: Concurrent tabs with a shared property id
    When tenant-a and tenant-b both cache revenue for prop-001
    Then two distinct cache entries must exist
    And each tab must show only its own tenant's total
