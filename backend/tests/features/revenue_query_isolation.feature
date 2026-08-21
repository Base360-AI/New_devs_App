Feature: DB query isolation for revenue
  Virtual tenancy shares tables. Property IDs are not globally unique.
  Every revenue query must bind tenant_id so one company cannot see another.

  Background:
    Given the assignment seed reservations are loaded

  Scenario: Tenant A only sees Tenant A reservations for a shared property id
    When tenant "tenant-a" requests lifetime revenue for property "prop-001"
    Then the revenue total is 2250.000
    And the reservation count is 4

  Scenario: Same property_id does not leak Tenant A data to Tenant B
    When tenant "tenant-b" requests lifetime revenue for property "prop-001"
    Then the revenue total is 0.000
    And the reservation count is 0

  Scenario: Monthly query binds tenant_id and excludes the other tenant
    When tenant "tenant-a" calculates monthly revenue for property "prop-001" in March 2024
    Then the monthly total is 2250.000
    And the last revenue query bound tenant_id "tenant-a"

  Scenario: Tenant B monthly total for the shared property id is empty
    When tenant "tenant-b" calculates monthly revenue for property "prop-001" in March 2024
    Then the monthly total is 0.000
    And the last revenue query bound tenant_id "tenant-b"

  Scenario: Unavailable database must not return another tenant's mock totals
    Given the database pool is unavailable
    When tenant "tenant-b" requests lifetime revenue for property "prop-001"
    Then the revenue total is 0.000
    And the reservation count is 0
