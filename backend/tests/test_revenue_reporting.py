import os
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from app.services.reservations import (
    calculate_total_revenue,
    format_currency_total,
    list_tenant_properties,
    report_period_utc,
)


class RevenuePeriodTests(unittest.TestCase):
    def test_paris_march_period_includes_local_midnight_boundary(self):
        start, end = report_period_utc(2024, 3, "Europe/Paris")

        self.assertEqual(datetime(2024, 2, 29, 23, tzinfo=timezone.utc), start)
        self.assertEqual(datetime(2024, 3, 31, 22, tzinfo=timezone.utc), end)

    def test_new_york_march_period_accounts_for_dst(self):
        start, end = report_period_utc(2024, 3, "America/New_York")

        self.assertEqual(datetime(2024, 3, 1, 5, tzinfo=timezone.utc), start)
        self.assertEqual(datetime(2024, 4, 1, 4, tzinfo=timezone.utc), end)


class CurrencyPrecisionTests(unittest.TestCase):
    def test_binary_float_edge_is_rounded_from_decimal(self):
        self.assertEqual("1.01", format_currency_total(Decimal("1.005")))

    def test_fractional_amounts_aggregate_exactly(self):
        total = Decimal("333.333") + Decimal("333.333") + Decimal("333.334")
        self.assertEqual("1000.00", format_currency_total(total))


@unittest.skipUnless(os.getenv("DATABASE_URL"), "requires the Docker Postgres database")
class SeededRevenueIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_seeded_march_totals_use_each_property_timezone(self):
        sunset = await calculate_total_revenue("prop-001", "tenant-a", 3, 2024)
        ocean = await calculate_total_revenue("prop-001", "tenant-b", 3, 2024)

        self.assertEqual("2250.00", sunset["total"])
        self.assertEqual(4, sunset["count"])
        self.assertEqual("0.00", ocean["total"])
        self.assertEqual(0, ocean["count"])

    async def test_tenant_cannot_query_another_tenants_unique_property(self):
        ocean_asking_for_sunset = await calculate_total_revenue(
            "prop-002", "tenant-b", 3, 2024
        )
        sunset_asking_for_ocean = await calculate_total_revenue(
            "prop-004", "tenant-a", 3, 2024
        )

        self.assertEqual("0.00", ocean_asking_for_sunset["total"])
        self.assertEqual(0, ocean_asking_for_sunset["count"])
        self.assertEqual("0.00", sunset_asking_for_ocean["total"])
        self.assertEqual(0, sunset_asking_for_ocean["count"])

    async def test_property_lists_are_tenant_scoped(self):
        sunset_ids = {item["id"] for item in await list_tenant_properties("tenant-a")}
        ocean_ids = {item["id"] for item in await list_tenant_properties("tenant-b")}

        self.assertEqual({"prop-001", "prop-002", "prop-003"}, sunset_ids)
        self.assertEqual({"prop-001", "prop-004", "prop-005"}, ocean_ids)
