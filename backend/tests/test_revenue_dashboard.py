import json
import unittest
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfoNotFoundError
import jwt
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.config import settings
from app.core.database_pool import db_pool
from app.core.tenant_resolver import TenantResolver
from app.services.reservations import (
    get_month_utc_range,
    calculate_monthly_revenue,
    get_tenant_properties,
    PropertyNotFoundError,
    MixedCurrencyError,
)
from app.services.cache import get_revenue_cache_key, get_revenue_summary


class MockRedisClient:
    """Mock Redis client for testing cache isolation without Redis dependency."""
    def __init__(self):
        self.store = {}

    async def get(self, key: str):
        return self.store.get(key)

    async def set(self, key: str, value, ttl: int = 300, ex: int = None):
        self.store[key] = value
        return True


class TestTimezoneBoundaryClassification(unittest.TestCase):
    """
    Tests timezone-aware calendar month boundary construction.
    Seed data booking '2024-02-29 23:30:00+00' is in March for Paris, but Feb for NY.
    """

    def test_paris_timezone_march_boundary(self):
        start_utc, end_utc = get_month_utc_range(2024, 3, "Europe/Paris")

        # March 1, 2024 00:00:00 in Paris (CET, UTC+1) is 2024-02-29 23:00:00 UTC
        expected_start = datetime(2024, 2, 29, 23, 0, 0, tzinfo=timezone.utc)
        # April 1, 2024 00:00:00 in Paris (CEST, UTC+2 after DST) is 2024-03-31 22:00:00 UTC
        expected_end = datetime(2024, 3, 31, 22, 0, 0, tzinfo=timezone.utc)

        self.assertEqual(start_utc, expected_start)
        self.assertEqual(end_utc, expected_end)

        # Boundary booking from seed: 2024-02-29 23:30:00 UTC
        booking_tz_1 = datetime(2024, 2, 29, 23, 30, 0, tzinfo=timezone.utc)
        self.assertTrue(start_utc <= booking_tz_1 < end_utc, "res-tz-1 must belong to March for Paris")

        # Booking 31 minutes earlier belongs to February in Paris
        feb_booking = datetime(2024, 2, 29, 22, 59, 0, tzinfo=timezone.utc)
        self.assertFalse(start_utc <= feb_booking < end_utc, "22:59 UTC must be in Feb for Paris")

        # Booking at April 1 00:00:00 Paris time (22:00 UTC) belongs to April (half-open interval)
        april_booking = datetime(2024, 3, 31, 22, 0, 0, tzinfo=timezone.utc)
        self.assertFalse(start_utc <= april_booking < end_utc, "April 1 00:00 Paris local time must be excluded")

    def test_new_york_timezone_march_boundary(self):
        start_utc, end_utc = get_month_utc_range(2024, 3, "America/New_York")

        # March 1, 2024 00:00:00 in New York (EST, UTC-5) is 2024-03-01 05:00:00 UTC
        expected_start = datetime(2024, 3, 1, 5, 0, 0, tzinfo=timezone.utc)
        # April 1, 2024 00:00:00 in New York (EDT, UTC-4 after DST) is 2024-04-01 04:00:00 UTC
        expected_end = datetime(2024, 4, 1, 4, 0, 0, tzinfo=timezone.utc)

        self.assertEqual(start_utc, expected_start)
        self.assertEqual(end_utc, expected_end)

        # 2024-02-29 23:30:00 UTC is Feb 29 18:30 in New York -> must NOT be in March
        booking_tz_1 = datetime(2024, 2, 29, 23, 30, 0, tzinfo=timezone.utc)
        self.assertFalse(start_utc <= booking_tz_1 < end_utc, "res-tz-1 must NOT belong to March for New York")

    def test_year_rollover_december_to_january(self):
        start_utc, end_utc = get_month_utc_range(2024, 12, "UTC")
        self.assertEqual(start_utc, datetime(2024, 12, 1, 0, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(end_utc, datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc))

    def test_invalid_timezone_fails_loudly(self):
        """Must fail loudly for invalid or unknown IANA timezone data instead of falling back to UTC."""
        with self.assertRaises(ZoneInfoNotFoundError):
            get_month_utc_range(2024, 3, "Invalid/Unknown_Timezone")

        with self.assertRaises(ZoneInfoNotFoundError):
            get_month_utc_range(2024, 3, "")


class TestDecimalPrecision(unittest.TestCase):
    """
    Tests financial cent precision and Decimal quantization behavior.
    """

    def test_subcent_summation_preserves_accuracy(self):
        # The 3 seed items with sub-cent decimals:
        # res-dec-1: 333.333
        # res-dec-2: 333.333
        # res-dec-3: 333.334
        # Plus res-tz-1: 1250.000
        amounts = [Decimal("333.333"), Decimal("333.333"), Decimal("333.334"), Decimal("1250.000")]
        total = sum(amounts)
        self.assertEqual(total, Decimal("2250.000"))

        # Quantize once at reporting boundary using ROUND_HALF_UP
        quantized = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        self.assertEqual(quantized, Decimal("2250.00"))
        self.assertEqual(f"{quantized:.2f}", "2250.00")

    def test_quantize_rounding_boundary(self):
        val_round_down = Decimal("100.004").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        val_round_up = Decimal("100.005").quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        self.assertEqual(str(val_round_down), "100.00")
        self.assertEqual(str(val_round_up), "100.01")


class TestCacheIsolation(unittest.IsolatedAsyncioTestCase):
    """
    Tests cache key scoping to ensure cross-tenant and period isolation.
    """

    async def asyncTearDown(self):
        await db_pool.close()

    def test_cache_keys_are_tenant_and_period_scoped(self):
        key_a = get_revenue_cache_key("tenant-a", "prop-001", 2024, 3)
        key_b = get_revenue_cache_key("tenant-b", "prop-001", 2024, 3)
        key_a_next_month = get_revenue_cache_key("tenant-a", "prop-001", 2024, 4)
        key_a_next_year = get_revenue_cache_key("tenant-a", "prop-001", 2025, 3)

        self.assertEqual(key_a, "revenue:tenant-a:prop-001:2024:3")
        self.assertEqual(key_b, "revenue:tenant-b:prop-001:2024:3")
        self.assertNotEqual(key_a, key_b, "Tenant A and Tenant B must have distinct cache keys")
        self.assertNotEqual(key_a, key_a_next_month, "Different months must have distinct cache keys")
        self.assertNotEqual(key_a, key_a_next_year, "Different years must have distinct cache keys")

    async def test_cache_data_never_shared_across_tenants(self):
        mock_redis = MockRedisClient()

        # Populate cache directly for tenant-a
        data_a = {
            "property_id": "prop-001",
            "tenant_id": "tenant-a",
            "year": 2024,
            "month": 3,
            "total": "2250.00",
            "currency": "USD",
            "count": 4,
        }
        await mock_redis.set("revenue:tenant-a:prop-001:2024:3", data_a)

        # Tenant-B requests summary for prop-001 with custom redis
        result_b = await get_revenue_summary(
            property_id="prop-001",
            tenant_id="tenant-b",
            year=2024,
            month=3,
            custom_redis=mock_redis
        )

        # Tenant B must see its own data (0.00, 0), NOT Tenant A's cached data!
        self.assertEqual(result_b["tenant_id"], "tenant-b")
        self.assertEqual(result_b["total"], "0.00")
        self.assertEqual(result_b["count"], 0)

    async def test_mismatched_cached_payload_rejected_and_overwritten(self):
        """Mismatched cached payload must never be returned and must be overwritten with recalculated data."""
        mock_redis = MockRedisClient()
        cache_key = get_revenue_cache_key("tenant-b", "prop-001", 2024, 3)

        # Poison the cache key for tenant-b with tenant-a's payload
        poisoned_payload = {
            "property_id": "prop-001",
            "tenant_id": "tenant-a",
            "year": 2024,
            "month": 3,
            "total": "999999.00",
            "currency": "USD",
            "count": 99,
        }
        await mock_redis.set(cache_key, poisoned_payload)

        # Request summary for tenant-b
        result = await get_revenue_summary(
            property_id="prop-001",
            tenant_id="tenant-b",
            year=2024,
            month=3,
            custom_redis=mock_redis
        )

        # Mismatched payload must NOT be served; live calculation for tenant-b must be returned
        self.assertEqual(result["tenant_id"], "tenant-b")
        self.assertEqual(result["total"], "0.00")
        self.assertEqual(result["count"], 0)

        # Cache entry should now be overwritten with valid tenant-b data
        cached_entry = await mock_redis.get(cache_key)
        self.assertIsNotNone(cached_entry)
        if isinstance(cached_entry, str):
            cached_entry = json.loads(cached_entry)
        self.assertEqual(cached_entry["tenant_id"], "tenant-b")
        self.assertEqual(cached_entry["total"], "0.00")


class TestTenantResolutionAndFailsClosed(unittest.IsolatedAsyncioTestCase):
    """
    Tests that tenant resolution fails closed for missing or unknown tenants.
    """

    async def test_known_emails_resolve(self):
        tenant_sunset = await TenantResolver.resolve_tenant_id(user_id="u1", user_email="sunset@propertyflow.com")
        tenant_ocean = await TenantResolver.resolve_tenant_id(user_id="u2", user_email="ocean@propertyflow.com")
        self.assertEqual(tenant_sunset, "tenant-a")
        self.assertEqual(tenant_ocean, "tenant-b")

    async def test_unknown_email_fails_closed(self):
        tenant_unknown = await TenantResolver.resolve_tenant_id(user_id="u3", user_email="unknown@randomcorp.com")
        self.assertIsNone(tenant_unknown, "Unknown users must resolve to None, not tenant-a")

        tenant_candidate = await TenantResolver.resolve_tenant_id(user_id="u4", user_email="candidate@propertyflow.com")
        self.assertIsNone(tenant_candidate, "Candidate account without tenant claim must resolve to None")

    def test_api_fails_closed_when_unauthenticated_or_missing_tenant(self):
        client = TestClient(app)

        # 1. Unauthenticated request -> 401
        res_no_auth = client.get("/api/v1/dashboard/summary?property_id=prop-001")
        self.assertEqual(res_no_auth.status_code, 401)

        # 2. Token without tenant claim -> 403 Forbidden
        token_no_tenant = jwt.encode(
            {"id": "unknown-user", "email": "stranger@unknown.com", "aud": "authenticated"},
            settings.secret_key,
            algorithm="HS256"
        )
        res_no_tenant = client.get(
            "/api/v1/dashboard/summary?property_id=prop-001",
            headers={"Authorization": f"Bearer {token_no_tenant}"}
        )
        self.assertEqual(res_no_tenant.status_code, 403)
        self.assertIn("valid tenant", res_no_tenant.json().get("detail", ""))


class TestDatabaseLiveExecutionAndSeedAcceptance(unittest.IsolatedAsyncioTestCase):
    """
    Verifies live PostgreSQL queries against actual seed data and acceptance targets.
    """

    async def asyncTearDown(self):
        await db_pool.close()

    async def test_sunset_acceptance_target(self):
        """Sunset / tenant-a / prop-001: revenue = 2250.00, count = 4"""
        data = await calculate_monthly_revenue("prop-001", "tenant-a", year=2024, month=3)
        self.assertEqual(data["property_id"], "prop-001")
        self.assertEqual(data["tenant_id"], "tenant-a")
        self.assertEqual(data["total"], "2250.00")
        self.assertEqual(data["currency"], "USD")
        self.assertEqual(data["count"], 4)

    async def test_ocean_acceptance_target(self):
        """Ocean / tenant-b / prop-001: revenue = 0.00, count = 0"""
        data = await calculate_monthly_revenue("prop-001", "tenant-b", year=2024, month=3)
        self.assertEqual(data["property_id"], "prop-001")
        self.assertEqual(data["tenant_id"], "tenant-b")
        self.assertEqual(data["total"], "0.00")
        self.assertEqual(data["currency"], "USD")
        self.assertEqual(data["count"], 0)

    async def test_foreign_property_access_rejected(self):
        """Foreign property access must raise PropertyNotFoundError (reject cross-tenant snooping)"""
        with self.assertRaises(PropertyNotFoundError):
            # prop-002 belongs to tenant-a, tenant-b cannot access it
            await calculate_monthly_revenue("prop-002", "tenant-b", year=2024, month=3)

        with self.assertRaises(PropertyNotFoundError):
            # prop-004 belongs to tenant-b, tenant-a cannot access it
            await calculate_monthly_revenue("prop-004", "tenant-a", year=2024, month=3)

    async def test_tenant_properties_dropdown_isolation(self):
        """Property dropdown query must be strictly tenant-scoped"""
        sunset_props = await get_tenant_properties("tenant-a")
        ocean_props = await get_tenant_properties("tenant-b")

        sunset_ids = {p["id"] for p in sunset_props}
        ocean_ids = {p["id"] for p in ocean_props}

        self.assertEqual(sunset_ids, {"prop-001", "prop-002", "prop-003"})
        self.assertEqual(ocean_ids, {"prop-001", "prop-004", "prop-005"})

        # Verify names and timezones
        sunset_map = {p["id"]: p for p in sunset_props}
        ocean_map = {p["id"]: p for p in ocean_props}
        self.assertEqual(sunset_map["prop-001"]["name"], "Beach House Alpha")
        self.assertEqual(sunset_map["prop-001"]["timezone"], "Europe/Paris")
        self.assertEqual(ocean_map["prop-001"]["name"], "Mountain Lodge Beta")
        self.assertEqual(ocean_map["prop-001"]["timezone"], "America/New_York")

    async def test_mixed_currency_rejection(self):
        """Reservations with multiple currencies for the period must fail explicitly."""
        async with db_pool.get_session() as session:
            try:
                # Insert reservations in May 2024 (isolated from March seed data) with mixed currencies
                await session.execute(text("""
                    INSERT INTO reservations (id, property_id, tenant_id, check_in_date, check_out_date, total_amount, currency)
                    VALUES
                        ('test-curr-usd', 'prop-001', 'tenant-a', '2024-05-10 12:00:00+00', '2024-05-12 10:00:00+00', 100.00, 'USD'),
                        ('test-curr-eur', 'prop-001', 'tenant-a', '2024-05-15 12:00:00+00', '2024-05-18 10:00:00+00', 150.00, 'EUR')
                """))
                await session.commit()

                with self.assertRaises(MixedCurrencyError):
                    await calculate_monthly_revenue("prop-001", "tenant-a", year=2024, month=5)
            finally:
                await session.execute(text("DELETE FROM reservations WHERE id IN ('test-curr-usd', 'test-curr-eur')"))
                await session.commit()

    async def test_single_non_usd_currency_derived(self):
        """Single non-USD currency is preserved and derived directly from queried rows."""
        async with db_pool.get_session() as session:
            try:
                # Insert a EUR reservation in June 2024
                await session.execute(text("""
                    INSERT INTO reservations (id, property_id, tenant_id, check_in_date, check_out_date, total_amount, currency)
                    VALUES ('test-curr-eur-only', 'prop-001', 'tenant-a', '2024-06-10 12:00:00+00', '2024-06-12 10:00:00+00', 250.00, 'EUR')
                """))
                await session.commit()

                data = await calculate_monthly_revenue("prop-001", "tenant-a", year=2024, month=6)
                self.assertEqual(data["currency"], "EUR")
                self.assertEqual(data["total"], "250.00")
                self.assertEqual(data["count"], 1)
            finally:
                await session.execute(text("DELETE FROM reservations WHERE id = 'test-curr-eur-only'"))
                await session.commit()


if __name__ == "__main__":
    unittest.main()
