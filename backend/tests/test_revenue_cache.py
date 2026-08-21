import json
import unittest
from unittest.mock import AsyncMock, patch

from app.services import cache


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        value = self.values.get(key)
        return value.encode() if value is not None else None

    async def setex(self, key, _ttl, value):
        self.values[key] = value


class RevenueCacheIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_cache_is_isolated_by_tenant_property_and_period(self):
        fake_redis = FakeRedis()

        async def calculate(property_id, tenant_id, month, year):
            total = "2250.00" if tenant_id == "tenant-a" else "0.00"
            return {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "total": total,
                "currency": "USD",
                "count": 4 if tenant_id == "tenant-a" else 0,
            }

        calculator = AsyncMock(side_effect=calculate)
        with patch.object(cache, "redis_client", fake_redis), patch(
            "app.services.reservations.calculate_total_revenue", calculator
        ):
            sunset = await cache.get_revenue_summary("prop-001", "tenant-a", 3, 2024)
            ocean = await cache.get_revenue_summary("prop-001", "tenant-b", 3, 2024)
            sunset_again = await cache.get_revenue_summary("prop-001", "tenant-a", 3, 2024)
            ocean_again = await cache.get_revenue_summary("prop-001", "tenant-b", 3, 2024)

        self.assertEqual("2250.00", sunset["total"])
        self.assertEqual("0.00", ocean["total"])
        self.assertEqual(sunset, sunset_again)
        self.assertEqual(ocean, ocean_again)
        self.assertEqual(2, calculator.await_count)
        self.assertEqual(
            {
                "revenue:tenant-a:prop-001:2024-03",
                "revenue:tenant-b:prop-001:2024-03",
            },
            set(fake_redis.values),
        )
        self.assertEqual(
            "tenant-a",
            json.loads(fake_redis.values["revenue:tenant-a:prop-001:2024-03"])["tenant_id"],
        )
        self.assertEqual(
            "tenant-b",
            json.loads(fake_redis.values["revenue:tenant-b:prop-001:2024-03"])["tenant_id"],
        )
