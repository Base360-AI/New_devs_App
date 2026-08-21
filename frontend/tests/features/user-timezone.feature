Feature: User timezone vs property timezone
  User-visible times use the profile timezone; revenue month windows stay on the property timezone.

  Scenario: Profile timezone differs from the browser
    When the user's profile timezone is America/New_York
    And the browser reports Europe/Paris
    Then user-facing timestamps must render in America/New_York

  Scenario: Missing profile timezone
    When the profile has no timezone
    Then the UI must fall back to UTC
    And it must not invent a company-wide default from another tenant

  Scenario: Paris property on a New York user
    When tenant-a views March revenue for prop-001 (Europe/Paris)
    And the user's profile timezone is America/New_York
    Then the March window must still include the booking at 2024-02-29 23:30:00+00
    And the displayed March total must be 2250.000

  Scenario: Browser zone must not shrink March
    When the browser timezone would treat a booking as February
    And the property timezone treats that booking as March
    Then the dashboard March total must still include the booking
