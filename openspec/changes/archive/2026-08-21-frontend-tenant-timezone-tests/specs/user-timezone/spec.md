## Purpose

Separates the user's profile timezone for display from the property timezone used for board-month revenue so March totals stay accurate and clocks match the signed-in user.

## ADDED Requirements

### Requirement: Display times use the profile timezone
User-visible dates and times on the dashboard and profile MUST use the signed-in user's stored profile timezone. They MUST NOT silently substitute the browser's detected timezone when a profile timezone is set.

#### Scenario: Profile timezone differs from the browser
- **WHEN** the user's profile timezone is America/New_York
- **AND** the browser reports Europe/Paris
- **THEN** user-facing timestamps MUST render in America/New_York

#### Scenario: Missing profile timezone
- **WHEN** the profile has no timezone
- **THEN** the UI MUST fall back to UTC
- **AND** it MUST NOT invent a company-wide default from another tenant

### Requirement: Revenue months stay on the property timezone
Monthly revenue shown for a property MUST follow that property's timezone. The client MUST NOT rewrite the month window using the browser timezone or the user's profile timezone.

#### Scenario: Paris property on a New York user
- **WHEN** tenant-a views March revenue for prop-001 (Europe/Paris)
- **AND** the user's profile timezone is America/New_York
- **THEN** the March window MUST still include the booking at 2024-02-29 23:30:00+00
- **AND** the displayed March total MUST be 2250.000

#### Scenario: Browser zone must not shrink March
- **WHEN** the browser timezone would treat a booking as February
- **AND** the property timezone treats that booking as March
- **THEN** the dashboard March total MUST still include the booking

### Requirement: Frontend tests lock timezone contracts
The frontend test suite MUST include scenarios for profile-timezone display and property-timezone revenue months.

#### Scenario: Timezone suite exists
- **WHEN** the frontend test suite runs
- **THEN** scenarios for profile display timezone and property-month revenue MUST execute
- **AND** they MUST fail if the UI uses the browser zone for either contract
