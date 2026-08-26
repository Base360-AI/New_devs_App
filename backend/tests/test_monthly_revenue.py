import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from app.services.reservations import (
    PropertyNotFoundError,
    calculate_monthly_revenue,
)


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeSession:
    def __init__(self, row):
        self.row = row
        self.query = None
        self.parameters = None

    async def execute(self, query, parameters):
        self.query = str(query)
        self.parameters = parameters
        return FakeResult(self.row)


class FakeSessionContext:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc_value, traceback):
        return False


class FakePool:
    def __init__(self, session):
        self.session = session
        self.session_factory = True

    async def initialize(self):
        return None

    def get_session(self):
        return FakeSessionContext(self.session)


class MonthlyRevenueTests(unittest.IsolatedAsyncioTestCase):
    async def test_monthly_query_uses_property_timezone_and_decimal_string(self):
        row = SimpleNamespace(
            property_id="prop-001",
            total_revenue=Decimal("2250.00"),
            reservation_count=4,
            currency="USD",
            currency_count=1,
        )
        session = FakeSession(row)

        with patch("app.core.database_pool.db_pool", FakePool(session)):
            summary = await calculate_monthly_revenue(
                "prop-001", "tenant-a", 3, 2024
            )

        self.assertEqual(summary["total"], "2250.00")
        self.assertEqual(summary["count"], 4)
        self.assertIn("AT TIME ZONE p.timezone", session.query)
        self.assertEqual(
            session.parameters["month_start"].isoformat(),
            "2024-03-01T00:00:00",
        )
        self.assertEqual(
            session.parameters["month_end"].isoformat(),
            "2024-04-01T00:00:00",
        )

    async def test_foreign_or_unknown_property_is_not_found(self):
        session = FakeSession(None)

        with patch("app.core.database_pool.db_pool", FakePool(session)):
            with self.assertRaises(PropertyNotFoundError):
                await calculate_monthly_revenue(
                    "prop-004", "tenant-a", 3, 2024
                )


if __name__ == "__main__":
    unittest.main()
