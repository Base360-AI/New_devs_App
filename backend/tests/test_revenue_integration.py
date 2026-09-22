"""Opt-in integration tests against the assignment Docker Compose environment."""
import json
import os
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch

import httpx
import redis
from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import dashboard
from app.core.database_pool import DatabasePool
from app.models.auth import AuthenticatedUser
from app.services import cache, reservations
from test_revenue import MemoryRedis


INTEGRATION = os.getenv("RUN_REVENUE_INTEGRATION") == "1"


@unittest.skipUnless(INTEGRATION, "Set RUN_REVENUE_INTEGRATION=1 with PostgreSQL available")
class PostgreSQLRevenueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pool = DatabasePool()
        await self.pool.initialize()
        self.connection = await self.pool.engine.connect()
        self.transaction = await self.connection.begin()
        self.tenant_a = "revenue-test-a-" + uuid4().hex
        self.tenant_b = "revenue-test-b-" + uuid4().hex
        self.property_id = "shared-test-property"
        for tenant, name, zone in [(self.tenant_a, "Paris test", "Europe/Paris"),
                                    (self.tenant_b, "NY test", "America/New_York")]:
            await self.connection.execute(text("INSERT INTO tenants (id,name) VALUES (:id,:name)"),
                                          dict(id=tenant, name=name))
            await self.connection.execute(text("""
                INSERT INTO properties (id,tenant_id,name,timezone) VALUES (:id,:tenant,:name,:zone)
            """), dict(id=self.property_id, tenant=tenant, name=name, zone=zone))
        # Service sessions share the outer transaction; all fixture writes are rolled back.
        self.session_patch = patch.object(self.pool, "get_session", side_effect=lambda:
            AsyncSession(bind=self.connection, join_transaction_mode="create_savepoint"))
        self.pool_patch = patch.object(reservations, "db_pool", self.pool)
        self.redis_patch = patch.object(cache, "redis_client", MemoryRedis())
        for item in [self.session_patch, self.pool_patch, self.redis_patch]:
            item.start()
        app = FastAPI()
        app.include_router(dashboard.router, prefix="/api/v1")
        app.dependency_overrides[dashboard.get_current_user] = lambda: AuthenticatedUser(
            id="fixture", email="fixture@example.com", permissions=[], cities=[],
            is_admin=False, tenant_id=self.tenant_a)
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        for item in [self.session_patch, self.pool_patch, self.redis_patch]:
            item.stop()
        await self.transaction.rollback()
        await self.connection.close()
        await self.pool.close()

    async def add_reservation(self, date, amount, tenant=None, currency="USD"):
        check_in = datetime.fromisoformat(date)
        await self.connection.execute(text("""
            INSERT INTO reservations
                (id,property_id,tenant_id,check_in_date,check_out_date,total_amount,currency)
            VALUES (:id,:property,:tenant,:start,:end,:amount,:currency)
        """), dict(id="revenue-test-" + uuid4().hex, property=self.property_id,
                   tenant=tenant or self.tenant_a, start=check_in, end=check_in + timedelta(days=1),
                   amount=Decimal(amount), currency=currency))

    async def api_summary(self, month):
        return await self.client.get("/api/v1/dashboard/summary",
            params=dict(property_id=self.property_id, month=month, year=2024))

    async def test_paris_half_open_month_boundaries_query_real_postgresql(self):
        for date, amount in [
            ("2024-02-29T22:59:59+00:00", "99"),
            ("2024-02-29T23:00:00+00:00", "1.005"),
            ("2024-02-29T23:30:00+00:00", "1250"),
            ("2024-03-31T21:59:59+00:00", "10.075"),
            ("2024-03-31T22:00:00+00:00", "20"),
            ("2024-04-01T00:00:00+00:00", "30"),
        ]:
            await self.add_reservation(date, amount)
        for month, total, count in [(2, "99.00", 1), (3, "1261.08", 3), (4, "50.00", 2)]:
            response = await self.api_summary(month)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["total_revenue"], total)
            self.assertEqual(response.json()["reservations_count"], count)

    async def test_numeric_sum_precedes_rounding(self):
        for amount in ["333.333", "333.333", "333.334"]:
            await self.add_reservation("2024-03-15T12:00:00+00:00", amount)
        self.assertEqual((await self.api_summary(3)).json()["total_revenue"], "1000.00")

    async def test_precision_edges_through_postgresql_cache_and_api(self):
        for month, amount, expected in [(1, "1.005", "1.01"), (2, "10.075", "10.08"),
                                        (3, "-1.005", "-1.01")]:
            await self.add_reservation(f"2024-{month:02d}-15T12:00:00+00:00", amount)
            # The second request exercises the cache hit as well.
            for _ in range(2):
                response = await self.api_summary(month)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["total_revenue"], expected)

    async def test_real_queries_isolate_shared_property_ids(self):
        await self.add_reservation("2024-03-15T12:00:00+00:00", "1250")
        await self.add_reservation("2024-03-15T12:00:00+00:00", "85", self.tenant_b)
        for tenant, expected in [(self.tenant_a, "1250.000"), (self.tenant_b, "85.000")]:
            result = await reservations.calculate_monthly_revenue(self.property_id, tenant, 3, 2024)
            self.assertEqual(result["total"], expected)
            properties = await reservations.list_revenue_properties(tenant)
            self.assertEqual([p["name"] for p in properties], ["Paris test" if tenant == self.tenant_a else "NY test"])

    async def test_missing_or_foreign_property_is_404(self):
        with self.assertRaises(HTTPException) as raised:
            await reservations.calculate_monthly_revenue(self.property_id, "unrelated-tenant", 3, 2024)
        self.assertEqual(raised.exception.status_code, 404)
        response = await self.client.get("/api/v1/dashboard/summary",
            params=dict(property_id="missing-property", month=3, year=2024))
        self.assertEqual(response.status_code, 404)

    async def test_valid_property_without_bookings_is_zero(self):
        response = await self.api_summary(4)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total_revenue"], "0.00")
        self.assertEqual(response.json()["reservations_count"], 0)

    async def test_mixed_currencies_are_not_added_together(self):
        await self.add_reservation("2024-03-15T12:00:00+00:00", "10", currency="USD")
        await self.add_reservation("2024-03-15T12:00:00+00:00", "10", currency="EUR")
        self.assertEqual((await self.api_summary(3)).status_code, 422)


@unittest.skipUnless(INTEGRATION, "Set RUN_REVENUE_INTEGRATION=1 with API, seed data and Redis available")
class LiveAssignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = httpx.Client(base_url=os.getenv("REVENUE_API_URL", "http://127.0.0.1:8000"), timeout=10)
        cls.headers = {}
        for tenant, email, password in [
            ("tenant-a", "sunset@propertyflow.com", "client_a_2024"),
            ("tenant-b", "ocean@propertyflow.com", "client_b_2024"),
        ]:
            response = cls.client.post("/api/v1/auth/login", json=dict(email=email, password=password))
            response.raise_for_status()
            cls.headers[tenant] = {"Authorization": "Bearer " + response.json()["access_token"]}
        cls.redis = redis.Redis.from_url(os.environ["REDIS_URL"], decode_responses=True)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.redis.close()

    def get_summary(self, tenant, property_id, month=3):
        return self.client.get("/api/v1/dashboard/summary", headers=self.headers[tenant],
            params=dict(property_id=property_id, month=month, year=2024))

    def test_both_accounts_seed_totals_and_month_separation(self):
        for tenant, property_id, total, count in [
            ("tenant-a", "prop-001", "2250.00", 4),
            ("tenant-a", "prop-002", "4975.50", 4),
            ("tenant-a", "prop-003", "6100.50", 2),
            ("tenant-b", "prop-001", "0.00", 0),
            ("tenant-b", "prop-004", "1776.50", 4),
            ("tenant-b", "prop-005", "3256.00", 3),
        ]:
            with self.subTest(tenant=tenant, property=property_id):
                march = self.get_summary(tenant, property_id)
                self.assertEqual(march.status_code, 200)
                self.assertEqual(march.json()["total_revenue"], total)
                self.assertEqual(march.json()["reservations_count"], count)
                april = self.get_summary(tenant, property_id, 4)
                self.assertEqual(april.status_code, 200)
                self.assertEqual(april.json()["total_revenue"], "0.00")
                self.assertEqual(april.json()["reservations_count"], 0)

    def test_real_redis_never_reuses_other_tenant_or_month(self):
        for tenant in ["tenant-a", "tenant-b", "tenant-a", "tenant-b"]:
            response = self.get_summary(tenant, "prop-001")
            self.assertEqual(response.json()["total_revenue"], "2250.00" if tenant == "tenant-a" else "0.00")
            key = cache.revenue_cache_key("prop-001", tenant, 3, 2024)
            cached = json.loads(self.redis.get(key))
            self.assertEqual(cached["tenant_id"], tenant)
            self.assertEqual((cached["month"], cached["year"]), (3, 2024))
            self.assertGreater(self.redis.ttl(key), 0)
        self.assertNotEqual(cache.revenue_cache_key("prop-001", "tenant-a", 3, 2024),
                            cache.revenue_cache_key("prop-001", "tenant-a", 4, 2024))

    def test_foreign_properties_remain_404_after_owner_populates_cache(self):
        for owner, other, prop in [("tenant-a", "tenant-b", "prop-002"),
                                   ("tenant-b", "tenant-a", "prop-004")]:
            self.assertEqual(self.get_summary(owner, prop).status_code, 200)
            self.assertEqual(self.get_summary(other, prop).status_code, 404)

    def test_property_selector_only_lists_authenticated_tenant_properties(self):
        for tenant, expected in [
            ("tenant-a", [("prop-001", "Beach House Alpha"), ("prop-002", "City Apartment Downtown"), ("prop-003", "Country Villa Estate")]),
            ("tenant-b", [("prop-001", "Mountain Lodge Beta"), ("prop-004", "Lakeside Cottage"), ("prop-005", "Urban Loft Modern")]),
        ]:
            response = self.client.get("/api/v1/dashboard/properties", headers=self.headers[tenant])
            self.assertEqual(response.status_code, 200)
            self.assertEqual([(p["id"], p["name"]) for p in response.json()], expected)

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.get("/api/v1/dashboard/summary",
            params=dict(property_id="prop-001", month=3, year=2024))
        self.assertEqual(response.status_code, 401)
