"""Focused regressions; standard-library unittest, no new test dependency."""
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1 import dashboard
from app.core.database_pool import DatabasePool
from app.models.auth import AuthenticatedUser
from app.services import cache
from app.services.reservations import monthly_utc_bounds


class MemoryRedis:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def setex(self, key, ttl, value):
        assert ttl == 300
        self.values[key] = value


def summary(property_id="prop-001", tenant_id="tenant-a", month=3, year=2024, total="2250.000"):
    return dict(property_id=property_id, tenant_id=tenant_id, month=month, year=year,
                total=total, currency="USD", count=4)


class RevenueCacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.redis = MemoryRedis()
        self.calculate = AsyncMock(side_effect=lambda p, t, m, y: summary(p, t, m, y))
        self.redis_patch = patch.object(cache, "redis_client", self.redis)
        self.calculate_patch = patch.object(cache, "calculate_monthly_revenue", self.calculate)
        self.redis_patch.start()
        self.calculate_patch.start()
        self.addCleanup(self.redis_patch.stop)
        self.addCleanup(self.calculate_patch.stop)

    async def test_same_property_id_is_isolated_in_both_request_orders(self):
        for tenants in [("tenant-a", "tenant-b"), ("tenant-b", "tenant-a")]:
            self.redis.values.clear()
            self.calculate.reset_mock()
            for tenant in (*tenants, *tenants):
                result = await cache.get_revenue_summary("prop-001", tenant, 3, 2024)
                self.assertEqual(result["tenant_id"], tenant)
            self.assertEqual(self.calculate.await_count, 2)
            self.assertEqual(len(self.redis.values), 2)

    async def test_cache_separates_months_and_years(self):
        for month, year in [(3, 2024), (4, 2024), (3, 2025)]:
            result = await cache.get_revenue_summary("prop-001", "tenant-a", month, year)
            self.assertEqual((result["month"], result["year"]), (month, year))
        self.assertEqual(len(self.redis.values), 3)

    async def test_legacy_cache_is_ignored(self):
        self.redis.values["revenue:prop-001"] = json.dumps(summary(tenant_id="tenant-b"))
        result = await cache.get_revenue_summary("prop-001", "tenant-a", 3, 2024)
        self.assertEqual(result["tenant_id"], "tenant-a")
        self.calculate.assert_awaited_once()

    async def test_mismatched_or_malformed_cache_is_recomputed(self):
        key = cache.revenue_cache_key("prop-001", "tenant-a", 3, 2024)
        bad_values = [
            json.dumps(summary(tenant_id="tenant-b")),
            json.dumps(summary(property_id="prop-002")),
            json.dumps(summary(month=4)), json.dumps(summary(year=2025)),
            "not json", "[]",
        ]
        for value in bad_values:
            with self.subTest(value=value):
                self.redis.values[key] = value
                result = await cache.get_revenue_summary("prop-001", "tenant-a", 3, 2024)
                self.assertEqual(result, summary())
        self.assertEqual(self.calculate.await_count, len(bad_values))

    async def test_database_error_does_not_return_or_cache_mock_revenue(self):
        self.calculate.side_effect = SQLAlchemyError("database unavailable")
        with self.assertRaises(SQLAlchemyError):
            await cache.get_revenue_summary("prop-001", "tenant-a", 3, 2024)
        self.assertEqual(self.redis.values, {})

    async def test_redis_failure_still_uses_real_calculation(self):
        with patch.object(self.redis, "get", AsyncMock(side_effect=RedisConnectionError())), \
             patch.object(self.redis, "setex", AsyncMock(side_effect=RedisConnectionError())):
            self.assertEqual(await cache.get_revenue_summary("prop-001", "tenant-a", 3, 2024), summary())

    def test_cache_key_components_cannot_collide(self):
        self.assertNotEqual(cache.revenue_cache_key("c", "a:b", 3, 2024),
                            cache.revenue_cache_key("b:c", "a", 3, 2024))


class MonthBoundaryTests(unittest.TestCase):
    def test_paris_march_includes_boundary_and_dst(self):
        start, end = monthly_utc_bounds(3, 2024, "Europe/Paris")
        self.assertEqual(start, datetime(2024, 2, 29, 23, tzinfo=timezone.utc))
        self.assertEqual(end, datetime(2024, 3, 31, 22, tzinfo=timezone.utc))
        self.assertLessEqual(start, datetime(2024, 2, 29, 23, 30, tzinfo=timezone.utc))
        self.assertEqual((end - start).total_seconds() / 3600, 743)

    def test_new_york_march_has_its_own_boundaries(self):
        self.assertEqual(monthly_utc_bounds(3, 2024, "America/New_York"), (
            datetime(2024, 3, 1, 5, tzinfo=timezone.utc),
            datetime(2024, 4, 1, 4, tzinfo=timezone.utc)))

    def test_december_rolls_into_next_year(self):
        self.assertEqual(monthly_utc_bounds(12, 2024, "Europe/Paris"), (
            datetime(2024, 11, 30, 23, tzinfo=timezone.utc),
            datetime(2024, 12, 31, 23, tzinfo=timezone.utc)))


class DatabasePoolTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_database_url_async_pool_and_session_lifecycle(self):
        pool = DatabasePool()
        try:
            await pool.initialize()
            engine = pool.engine
            await pool.initialize()
            self.assertIs(pool.engine, engine)
            self.assertEqual(engine.url.drivername, "postgresql+asyncpg")
            self.assertEqual(type(engine.pool).__name__, "AsyncAdaptedQueuePool")
            async with pool.get_session() as session:
                self.assertIs(session.bind, engine)
        finally:
            await pool.close()
        self.assertIsNone(pool.session_factory)
        self.assertIsNone(pool.engine)


class DashboardContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = FastAPI()
        self.app.include_router(dashboard.router, prefix="/api/v1")
        self.user = AuthenticatedUser(id="test", email="test@example.com", permissions=[],
                                      cities=[], is_admin=False, tenant_id="tenant-a")
        self.app.dependency_overrides[dashboard.get_current_user] = lambda: self.user
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test")
        self.calculate = AsyncMock(return_value=summary())
        self.mock = patch.object(dashboard, "get_revenue_summary", self.calculate)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_decimal_contract_and_half_up_edge_cases(self):
        for amount, expected in [("1.005", "1.01"), ("10.075", "10.08"),
                                 ("-1.005", "-1.01"), ("0", "0.00"),
                                 ("1000.000", "1000.00"), ("2250.000", "2250.00")]:
            with self.subTest(amount=amount):
                self.calculate.return_value = summary(total=amount)
                response = await self.client.get("/api/v1/dashboard/summary",
                    params=dict(property_id="prop-001", month=3, year=2024))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["total_revenue"], expected)
                self.assertEqual(response.json()["month"], 3)

    async def test_period_is_required_and_validated(self):
        for params in [{}, {"month": 0, "year": 2024}, {"month": 13, "year": 2024},
                       {"month": 3, "year": 0}, {"month": 3, "year": 9999}]:
            response = await self.client.get("/api/v1/dashboard/summary",
                params={"property_id": "prop-001", **params})
            self.assertEqual(response.status_code, 422)
        self.calculate.assert_not_awaited()

    async def test_missing_tenant_is_rejected_before_cache_access(self):
        self.user.tenant_id = None
        response = await self.client.get("/api/v1/dashboard/summary",
            params=dict(property_id="prop-001", month=3, year=2024))
        self.assertEqual(response.status_code, 403)
        self.calculate.assert_not_awaited()

    async def test_database_failure_is_503_not_successful_mock(self):
        self.calculate.side_effect = SQLAlchemyError("unavailable")
        response = await self.client.get("/api/v1/dashboard/summary",
            params=dict(property_id="prop-001", month=3, year=2024))
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("total_revenue", response.json())

    async def test_requested_tenant_comes_from_auth_not_simulation_header(self):
        await self.client.get("/api/v1/dashboard/summary",
            params=dict(property_id="prop-001", month=4, year=2024),
            headers={"X-Simulated-Tenant": "tenant-b"})
        self.calculate.assert_awaited_once_with("prop-001", "tenant-a", 4, 2024)
