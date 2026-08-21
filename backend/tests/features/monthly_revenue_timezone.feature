Feature: Monthly revenue uses the property timezone
  Board totals must match internal records in the property's local calendar.
  check_in_date is timestamptz; month windows must not be naive UTC.

  Background:
    Given the assignment seed reservations are loaded

  Scenario: UTC-February booking is March in Europe/Paris
    Given property "prop-001" for tenant "tenant-a" is in timezone "Europe/Paris"
    And reservation "res-tz-1" checks in at "2024-02-29 23:30:00+00"
    When tenant "tenant-a" calculates monthly revenue for property "prop-001" in March 2024
    Then reservation "res-tz-1" is included in the monthly total
    And the monthly total is 2250.000

  Scenario: Same instant stays February in America/New_York
    Given a booking "res-ny-boundary" of 100.000 on property "prop-001" for tenant "tenant-b" checking in at "2024-02-29 23:30:00+00"
    And property "prop-001" for tenant "tenant-b" is in timezone "America/New_York"
    When tenant "tenant-b" calculates monthly revenue for property "prop-001" in March 2024
    Then reservation "res-ny-boundary" is not included in the monthly total
    And the monthly total is 0.000

  Scenario: March window uses property-local bounds including DST
    Given a booking "res-dst-april" of 50.000 on property "prop-001" for tenant "tenant-a" checking in at "2024-03-31 22:30:00+00"
    And property "prop-001" for tenant "tenant-a" is in timezone "Europe/Paris"
    When tenant "tenant-a" calculates monthly revenue for property "prop-001" in March 2024
    Then reservation "res-dst-april" is not included in the monthly total
    And the monthly total is 2250.000

  Scenario: Month bounds are timezone-aware for Europe/Paris March 2024
    When the March 2024 window is built for timezone "Europe/Paris"
    Then the window start is "2024-03-01 00:00:00+01:00"
    And the window end is "2024-04-01 00:00:00+02:00"
