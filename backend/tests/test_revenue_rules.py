import unittest
from datetime import datetime, timezone
from decimal import Decimal

from app.services.reservations import format_money, month_bounds, quantize_money, revenue_cache_key


class RevenueRulesTest(unittest.TestCase):
    def test_paris_march_includes_late_utc_february_check_in(self):
        start, end = month_bounds(2024, 3, "Europe/Paris")
        check_in = datetime(2024, 2, 29, 23, 30, tzinfo=timezone.utc)
        utc_march = datetime(2024, 3, 1, tzinfo=timezone.utc)
        self.assertLess(check_in, utc_march)
        self.assertLessEqual(start, check_in)
        self.assertLess(check_in, end)

    def test_new_york_march_excludes_that_same_check_in(self):
        start, end = month_bounds(2024, 3, "America/New_York")
        check_in = datetime(2024, 2, 29, 23, 30, tzinfo=timezone.utc)
        self.assertFalse(start <= check_in < end)

    def test_subcent_bookings_round_after_sum(self):
        lines = [Decimal("333.333"), Decimal("333.333"), Decimal("333.334")]
        self.assertEqual(format_money(sum(lines, Decimal("0"))), "1000.00")
        self.assertEqual(
            sum((quantize_money(line) for line in lines), Decimal("0")),
            Decimal("999.99"),
        )

    def test_cache_key_isolates_shared_property_ids(self):
        sunset = revenue_cache_key("tenant-a", "prop-001", 2024, 3)
        ocean = revenue_cache_key("tenant-b", "prop-001", 2024, 3)
        self.assertNotEqual(sunset, ocean)


if __name__ == "__main__":
    unittest.main()