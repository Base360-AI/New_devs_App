# New_devs_App

This project contains a FastAPI backend and a React frontend.

## Dashboard Revenue Summary API

Endpoint:

- `GET /api/v1/dashboard/summary`

Required query parameters:

- `property_id` (string)

Optional query parameters:

- `month` (integer, `1-12`)
- `year` (integer, `2000-2100`)

Behavior:

- If `month` and `year` are omitted, the backend defaults to the current month and year.
- The request requires tenant context from the authenticated user.
- Revenue data is cached per tenant/property/month/year key.

Example request:

- `/api/v1/dashboard/summary?property_id=prop-001&month=4&year=2026`

Example response:

```json
{
  "property_id": "prop-001",
  "total_revenue": "2250.00",
  "currency": "MYR",
  "reservations_count": 4,
  "month": 4,
  "year": 2026
}
```

Notes:

- `total_revenue` is returned as a **string** to preserve currency precision.

## Development Notes

- Python cache artifacts are ignored via `.gitignore`:
  - `**/__pycache__/`
  - `*.py[cod]`

## Quick Verification Checklist

- Open dashboard in frontend and select a property, month, and year.
- Confirm request URL includes `property_id`, `month`, and `year`.
- Confirm invalid `month` (e.g. `13`) returns `400`.
- Confirm invalid `year` (e.g. `1900`) returns `400`.
- Confirm `total_revenue` in API response is a string with 2 decimal places.
