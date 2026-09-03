import json
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app.api.v1.dashboard import get_dashboard_summary
from app.services.cache import get_revenue_summary
from app.services.reservations import calculate_monthly_revenue, round_currency


class FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class FakeSession:
    def __init__(self, rows):
        self._rows = iter(rows)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def execute(self, statement, parameters):
        self.calls.append((str(statement), parameters))
        return FakeResult(next(self._rows))


class FakePool:
    def __init__(self, session):
        self.session_factory = object()
        self._session = session

    async def initialize(self):
        return None

    def get_session(self):
        return self._session


class MonthlyRevenueTests(unittest.IsolatedAsyncioTestCase):
    def test_rounds_only_after_aggregation(self):
        aggregated = Decimal("333.333") + Decimal("333.333") + Decimal("333.339")
        self.assertEqual(round_currency(aggregated), Decimal("1000.01"))

    async def test_explicit_period_uses_property_timezone_boundaries(self):
        session = FakeSession(
            [SimpleNamespace(total_revenue=Decimal("999.995"), reservation_count=3)]
        )
        fake_pool = FakePool(session)

        with patch("app.core.database_pool.DatabasePool", return_value=fake_pool):
            result = await calculate_monthly_revenue(
                "prop-001", "tenant-a", month=3, year=2024
            )

        self.assertEqual(result["total"], "1000.00")
        self.assertEqual(result["count"], 3)
        self.assertEqual((result["month"], result["year"]), (3, 2024))
        self.assertEqual(len(session.calls), 1)
        statement, parameters = session.calls[0]
        self.assertIn("r.check_in_date AT TIME ZONE p.timezone", statement)
        self.assertIn("p.tenant_id = r.tenant_id", statement)
        self.assertEqual(
            parameters["start_date"], datetime(2024, 3, 1)
        )
        self.assertEqual(
            parameters["end_date"], datetime(2024, 4, 1)
        )

    async def test_default_period_is_latest_available_month(self):
        session = FakeSession(
            [
                SimpleNamespace(month=3, year=2024),
                SimpleNamespace(total_revenue=Decimal("1776.500"), reservation_count=4),
            ]
        )
        fake_pool = FakePool(session)

        with patch("app.core.database_pool.DatabasePool", return_value=fake_pool):
            result = await calculate_monthly_revenue("prop-004", "tenant-b")

        self.assertEqual(result["total"], "1776.50")
        self.assertEqual((result["month"], result["year"]), (3, 2024))
        self.assertIn("r.check_in_date AT TIME ZONE p.timezone", session.calls[0][0])
        self.assertIn("p.tenant_id = r.tenant_id", session.calls[0][0])
        self.assertEqual(len(session.calls), 2)

    async def test_paris_boundary_booking_is_in_march(self):
        boundary_check_in = datetime(2024, 2, 29, 23, 30, tzinfo=timezone.utc)
        paris_check_in = boundary_check_in.astimezone(ZoneInfo("Europe/Paris"))
        self.assertEqual(
            paris_check_in,
            datetime(2024, 3, 1, 0, 30, tzinfo=ZoneInfo("Europe/Paris")),
        )

        session = FakeSession(
            [SimpleNamespace(total_revenue=Decimal("2250.000"), reservation_count=4)]
        )
        fake_pool = FakePool(session)

        with patch("app.core.database_pool.DatabasePool", return_value=fake_pool):
            result = await calculate_monthly_revenue(
                "prop-001", "tenant-a", month=3, year=2024
            )

        statement, parameters = session.calls[0]
        self.assertIn("p.id = r.property_id", statement)
        self.assertIn("p.tenant_id = r.tenant_id", statement)
        self.assertIn("r.check_in_date AT TIME ZONE p.timezone", statement)
        self.assertEqual(parameters["start_date"], datetime(2024, 3, 1))
        self.assertEqual(parameters["end_date"], datetime(2024, 4, 1))
        self.assertEqual(result["total"], "2250.00")
        self.assertEqual(result["count"], 4)

    async def test_no_available_period_returns_empty_summary(self):
        session = FakeSession([None])
        fake_pool = FakePool(session)

        with patch("app.core.database_pool.DatabasePool", return_value=fake_pool):
            result = await calculate_monthly_revenue("missing", "tenant-a")

        self.assertEqual(result["total"], "0.00")
        self.assertEqual(result["count"], 0)
        self.assertIsNone(result["month"])
        self.assertIsNone(result["year"])

    async def test_rejects_partial_period(self):
        with self.assertRaisesRegex(ValueError, "provided together"):
            await calculate_monthly_revenue(
                "prop-001", "tenant-a", month=3, year=None
            )

    async def test_dashboard_rejects_partial_period(self):
        with self.assertRaises(HTTPException) as raised:
            await get_dashboard_summary(
                property_id="prop-001",
                month=3,
                year=None,
                current_user=SimpleNamespace(tenant_id="tenant-a"),
            )

        self.assertEqual(raised.exception.status_code, 422)

    async def test_dashboard_returns_selected_period(self):
        summary = {
            "property_id": "prop-001",
            "tenant_id": "tenant-a",
            "total": "1000.00",
            "currency": "USD",
            "count": 3,
            "month": 3,
            "year": 2024,
        }

        with patch(
            "app.api.v1.dashboard.get_revenue_summary",
            new=AsyncMock(return_value=summary),
        ) as revenue_summary:
            result = await get_dashboard_summary(
                property_id="prop-001",
                month=3,
                year=2024,
                current_user=SimpleNamespace(tenant_id="tenant-a"),
            )

        revenue_summary.assert_awaited_once_with(
            "prop-001", "tenant-a", 3, 2024
        )
        self.assertEqual(result["total_revenue"], 1000.0)
        self.assertEqual((result["month"], result["year"]), (3, 2024))

    async def test_cache_delegates_selected_period_to_monthly_service(self):
        summary = {
            "property_id": "prop-001",
            "tenant_id": "tenant-a",
            "total": "1000.00",
            "currency": "USD",
            "count": 3,
            "month": 3,
            "year": 2024,
        }

        with (
            patch("app.services.cache.redis_client.get", new=AsyncMock(return_value=None)),
            patch("app.services.cache.redis_client.setex", new=AsyncMock()) as cache_set,
            patch(
                "app.services.reservations.calculate_monthly_revenue",
                new=AsyncMock(return_value=summary),
            ) as calculate,
        ):
            result = await get_revenue_summary(
                "prop-001", "tenant-a", month=3, year=2024
            )

        calculate.assert_awaited_once_with("prop-001", "tenant-a", 3, 2024)
        cache_set.assert_awaited_once_with(
            "revenue:prop-001", 300, json.dumps(summary)
        )
        self.assertEqual(result, summary)


if __name__ == "__main__":
    unittest.main()
