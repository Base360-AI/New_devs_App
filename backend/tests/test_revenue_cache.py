import json
import unittest
from unittest.mock import AsyncMock, patch

from app.services import cache


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def setex(self, key, _ttl, value):
        self.values[key] = value


class RevenueCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_property_is_isolated_between_tenants(self):
        fake_redis = FakeRedis()
        calculate = AsyncMock(
            side_effect=[
                {"property_id": "prop-shared", "tenant_id": "tenant-a", "total": "100.00"},
                {"property_id": "prop-shared", "tenant_id": "tenant-b", "total": "250.00"},
            ]
        )

        with (
            patch.object(cache, "redis_client", fake_redis),
            patch("app.services.reservations.calculate_total_revenue", calculate),
        ):
            tenant_a = await cache.get_revenue_summary("prop-shared", "tenant-a")
            tenant_b = await cache.get_revenue_summary("prop-shared", "tenant-b")

        self.assertEqual(tenant_a["total"], "100.00")
        self.assertEqual(tenant_b["total"], "250.00")
        self.assertEqual(calculate.await_count, 2)
        self.assertIn("revenue:tenant-a:prop-shared:latest", fake_redis.values)
        self.assertIn("revenue:tenant-b:prop-shared:latest", fake_redis.values)

    async def test_reporting_months_use_distinct_cache_entries(self):
        fake_redis = FakeRedis()
        calculate = AsyncMock(
            side_effect=[
                {"property_id": "prop-001", "tenant_id": "tenant-a", "total": "100.00"},
                {"property_id": "prop-001", "tenant_id": "tenant-a", "total": "200.00"},
            ]
        )

        with (
            patch.object(cache, "redis_client", fake_redis),
            patch("app.services.reservations.calculate_total_revenue", calculate),
        ):
            await cache.get_revenue_summary("prop-001", "tenant-a", month=2, year=2024)
            await cache.get_revenue_summary("prop-001", "tenant-a", month=3, year=2024)

        self.assertEqual(calculate.await_count, 2)
        self.assertIn("revenue:tenant-a:prop-001:2024-02", fake_redis.values)
        self.assertIn("revenue:tenant-a:prop-001:2024-03", fake_redis.values)

    async def test_cached_value_is_reused_within_same_tenant_and_period(self):
        cached = {
            "property_id": "prop-001",
            "tenant_id": "tenant-a",
            "total": "100.00",
        }
        fake_redis = FakeRedis()
        fake_redis.values["revenue:tenant-a:prop-001:2024-03"] = json.dumps(cached)
        calculate = AsyncMock()

        with (
            patch.object(cache, "redis_client", fake_redis),
            patch("app.services.reservations.calculate_total_revenue", calculate),
        ):
            result = await cache.get_revenue_summary(
                "prop-001", "tenant-a", month=3, year=2024
            )

        self.assertEqual(result, cached)
        calculate.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
