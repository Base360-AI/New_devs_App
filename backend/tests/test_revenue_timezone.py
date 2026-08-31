import unittest
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.services.reservations import (
    _month_boundaries_utc,
    calculate_monthly_revenue,
    calculate_monthly_revenue_summary,
)


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeSession:
    def __init__(self, total_revenue=Decimal("2250.000")):
        self.calls = []
        self.total_revenue = total_revenue

    async def execute(self, statement, params):
        self.calls.append((str(statement), params))
        if len(self.calls) == 1:
            return FakeResult(SimpleNamespace(timezone="Europe/Paris"))
        return FakeResult(
            SimpleNamespace(
                total_revenue=self.total_revenue,
                reservation_count=4,
                currency="USD",
            )
        )


class MonthlyRevenueTimezoneTests(unittest.IsolatedAsyncioTestCase):
    def test_paris_march_boundaries_account_for_dst(self):
        start_utc, end_utc = _month_boundaries_utc(
            2024,
            3,
            "Europe/Paris",
        )

        self.assertEqual(
            start_utc,
            datetime(2024, 2, 29, 23, tzinfo=timezone.utc),
        )
        self.assertEqual(
            end_utc,
            datetime(2024, 3, 31, 22, tzinfo=timezone.utc),
        )

    async def test_monthly_query_is_tenant_scoped(self):
        session = FakeSession()

        total = await calculate_monthly_revenue(
            "prop-001",
            "tenant-a",
            3,
            2024,
            session,
        )

        self.assertEqual(total, Decimal("2250.00"))
        self.assertEqual(session.calls[0][1]["tenant_id"], "tenant-a")
        self.assertEqual(session.calls[1][1]["tenant_id"], "tenant-a")
        self.assertEqual(
            session.calls[1][1]["start_utc"],
            datetime(2024, 2, 29, 23, tzinfo=timezone.utc),
        )
        self.assertEqual(
            session.calls[1][1]["end_utc"],
            datetime(2024, 3, 31, 22, tzinfo=timezone.utc),
        )

    async def test_total_is_rounded_half_up_and_serialized_as_fixed_point(self):
        session = FakeSession(Decimal("10.005"))

        summary = await calculate_monthly_revenue_summary(
            "prop-001",
            "tenant-a",
            3,
            2024,
            session,
        )

        self.assertEqual(summary["total"], "10.01")


if __name__ == "__main__":
    unittest.main()
