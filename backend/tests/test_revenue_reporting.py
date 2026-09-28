from datetime import datetime, timezone
from decimal import Decimal
import unittest

from app.services.revenue_reporting import format_money, month_bounds_utc, revenue_cache_key


class RevenueReportingTests(unittest.TestCase):
    def test_paris_month_bounds_include_the_utc_february_boundary_reservation(self) -> None:
        start_at, end_at = month_bounds_utc(2024, 3, "Europe/Paris")

        self.assertEqual(start_at, datetime(2024, 2, 29, 23, 0, tzinfo=timezone.utc))
        self.assertEqual(end_at, datetime(2024, 3, 31, 22, 0, tzinfo=timezone.utc))

        # res-tz-1: 2024-02-29 23:30 UTC is March 1 in Paris.
        reservation_check_in = datetime(2024, 2, 29, 23, 30, tzinfo=timezone.utc)
        self.assertGreaterEqual(reservation_check_in, start_at)
        self.assertLess(reservation_check_in, end_at)

    def test_decimal_amounts_are_summed_before_rounding_to_cents(self) -> None:
        march_total = sum(
            [
                Decimal("1250.000"),
                Decimal("333.333"),
                Decimal("333.333"),
                Decimal("333.334"),
            ]
        )

        self.assertEqual(format_money(march_total), "2250.00")
        self.assertEqual(format_money(Decimal("333.333") * 3), "1000.00")

    def test_revenue_cache_is_partitioned_by_tenant_and_reporting_period(self) -> None:
        sunset_key = revenue_cache_key("tenant-a", "prop-001", 2024, 3)
        ocean_key = revenue_cache_key("tenant-b", "prop-001", 2024, 3)
        april_key = revenue_cache_key("tenant-a", "prop-001", 2024, 4)

        self.assertNotEqual(sunset_key, ocean_key)
        self.assertNotEqual(sunset_key, april_key)

if __name__ == "__main__":
    unittest.main()
