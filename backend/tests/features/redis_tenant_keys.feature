Feature: Tenant-inclusive Redis keys for revenue
  Cache hits must be impossible across tenants.
  Revenue keys must include tenant_id, not only property_id.

  Background:
    Given the assignment seed reservations are loaded
    And a fake Redis client is used for revenue caching

  Scenario: Cache key is namespaced by tenant and property
    When tenant "tenant-a" caches revenue for property "prop-001"
    Then Redis has a key that contains both "tenant-a" and "prop-001"
    And Redis does not have the unscoped key "revenue:prop-001"

  Scenario: Tenant B refresh cannot read Tenant A cache
    Given tenant "tenant-a" has a warm revenue cache for property "prop-001"
    When tenant "tenant-b" requests cached revenue for property "prop-001"
    Then the revenue total is 0.000
    And the reservation count is 0

  Scenario: Two tenants can cache the same property id concurrently
    When tenant "tenant-a" caches revenue for property "prop-001"
    And tenant "tenant-b" caches revenue for property "prop-001"
    Then Redis stores two distinct keys for property "prop-001"
    And the cached payload for tenant "tenant-a" has total 2250.000
    And the cached payload for tenant "tenant-b" has total 0.000
