import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.api.v1.dashboard import get_dashboard_summary
from app.services.reservations import (
    RevenueDataUnavailableError,
    calculate_total_revenue,
)


class RevenueOutageTests(unittest.IsolatedAsyncioTestCase):
    async def test_database_error_never_returns_fabricated_revenue(self):
        with patch(
            "app.core.database_pool.db_pool.initialize",
            new=AsyncMock(side_effect=RuntimeError("database unavailable")),
        ):
            with self.assertRaises(RevenueDataUnavailableError):
                await calculate_total_revenue("prop-001", "tenant-a")

    async def test_dashboard_maps_database_error_to_retryable_503(self):
        with patch(
            "app.api.v1.dashboard.get_revenue_summary",
            new=AsyncMock(side_effect=RevenueDataUnavailableError()),
        ):
            with self.assertRaises(HTTPException) as raised:
                await get_dashboard_summary(
                    property_id="prop-001",
                    current_user=SimpleNamespace(tenant_id="tenant-a"),
                )

        self.assertEqual(raised.exception.status_code, 503)
        self.assertIn("try again", raised.exception.detail.lower())


if __name__ == "__main__":
    unittest.main()
