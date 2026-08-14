import json
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import redis
from fastapi import HTTPException

from app.api.v1 import dashboard
from app.services import cache
from app.services.reservations import (
    PropertyNotFoundError,
    RevenueServiceError,
    _month_boundaries_utc,
    calculate_total_revenue,
    get_properties_for_tenant,
)


class FakeMappings:
    def __init__(self, rows):
        self.rows = rows

    def first(self):
        return self.rows[0] if self.rows else None

    def one(self):
        if len(self.rows) != 1:
            raise AssertionError(f"expected exactly one row, got {len(self.rows)}")
        return self.rows[0]

    def all(self):
        return self.rows


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return FakeMappings(self.rows)


class FakeSession:
    def __init__(self, result_rows=None, error=None):
        self.result_rows = list(result_rows or [])
        self.error = error
        self.calls = []

    async def execute(self, statement, parameters):
        self.calls.append((str(statement), parameters))
        if self.error is not None:
            raise self.error
        if not self.result_rows:
            raise AssertionError("unexpected database call")
        return FakeResult(self.result_rows.pop(0))


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.get_calls = []
        self.setex_calls = []
        self.get_error = None

    async def get(self, key):
        self.get_calls.append(key)
        if self.get_error is not None:
            raise self.get_error
        return self.values.get(key)

    async def setex(self, key, ttl, value):
        self.setex_calls.append((key, ttl, value))
        self.values[key] = value


class RevenueServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_paris_march_boundaries_include_late_february_utc(self):
        start_utc, end_utc = _month_boundaries_utc(2024, 3, "Europe/Paris")

        self.assertEqual(start_utc, datetime(2024, 2, 29, 23, 0, tzinfo=timezone.utc))
        self.assertEqual(end_utc, datetime(2024, 3, 31, 22, 0, tzinfo=timezone.utc))
        boundary_reservation = datetime(
            2024, 2, 29, 23, 30, tzinfo=timezone.utc
        )
        self.assertLessEqual(start_utc, boundary_reservation)
        self.assertLess(boundary_reservation, end_utc)

    async def test_shared_property_id_remains_tenant_isolated(self):
        tenant_a_session = FakeSession(
            [
                [{"id": "prop-001", "name": "Beach House", "timezone": "Europe/Paris"}],
                [
                    {
                        "total_revenue": Decimal("2250.000"),
                        "reservation_count": 4,
                        "currency": "USD",
                        "currency_count": 1,
                    }
                ],
            ]
        )
        tenant_b_session = FakeSession(
            [
                [
                    {
                        "id": "prop-001",
                        "name": "Mountain Lodge",
                        "timezone": "America/New_York",
                    }
                ],
                [
                    {
                        "total_revenue": Decimal("0"),
                        "reservation_count": 0,
                        "currency": "USD",
                        "currency_count": 0,
                    }
                ],
            ]
        )

        tenant_a = await calculate_total_revenue(
            "prop-001", "tenant-a", 2024, 3, db_session=tenant_a_session
        )
        tenant_b = await calculate_total_revenue(
            "prop-001", "tenant-b", 2024, 3, db_session=tenant_b_session
        )

        self.assertEqual((tenant_a["total"], tenant_a["count"]), ("2250.00", 4))
        self.assertEqual((tenant_b["total"], tenant_b["count"]), ("0.00", 0))
        for session, expected_tenant in (
            (tenant_a_session, "tenant-a"),
            (tenant_b_session, "tenant-b"),
        ):
            self.assertEqual(len(session.calls), 2)
            self.assertEqual(session.calls[0][1]["tenant_id"], expected_tenant)
            self.assertEqual(session.calls[1][1]["tenant_id"], expected_tenant)
            self.assertEqual(session.calls[1][1]["property_id"], "prop-001")
            self.assertEqual(session.calls[1][1]["start_utc"].tzinfo, timezone.utc)
            self.assertEqual(session.calls[1][1]["end_utc"].tzinfo, timezone.utc)

    async def test_money_is_quantized_once_and_returned_as_two_decimal_text(self):
        session = FakeSession(
            [
                [{"id": "prop-002", "name": "Apartment", "timezone": "UTC"}],
                [
                    {
                        "total_revenue": Decimal("2.675"),
                        "reservation_count": 1,
                        "currency": "USD",
                        "currency_count": 1,
                    }
                ],
            ]
        )

        result = await calculate_total_revenue(
            "prop-002", "tenant-a", 2024, 3, db_session=session
        )

        self.assertEqual(result["total"], "2.68")
        self.assertIsInstance(result["total"], str)

    async def test_unknown_property_is_rejected_before_reservation_query(self):
        session = FakeSession([[]])

        with self.assertRaises(PropertyNotFoundError):
            await calculate_total_revenue(
                "prop-004", "tenant-a", 2024, 3, db_session=session
            )

        self.assertEqual(len(session.calls), 1)
        self.assertEqual(
            session.calls[0][1],
            {"property_id": "prop-004", "tenant_id": "tenant-a"},
        )

    async def test_database_failure_does_not_return_mock_revenue(self):
        session = FakeSession(error=RuntimeError("database unavailable"))

        with self.assertRaisesRegex(
            RevenueServiceError, "Revenue data is temporarily unavailable"
        ):
            await calculate_total_revenue(
                "prop-001", "tenant-a", 2024, 3, db_session=session
            )

    async def test_property_listing_is_scoped_by_tenant(self):
        session = FakeSession(
            [
                [
                    {
                        "id": "prop-001",
                        "name": "Beach House",
                        "timezone": "Europe/Paris",
                    }
                ]
            ]
        )

        properties = await get_properties_for_tenant(
            "tenant-a", db_session=session
        )

        self.assertEqual([item["name"] for item in properties], ["Beach House"])
        self.assertEqual(session.calls[0][1], {"tenant_id": "tenant-a"})


class RevenueCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_cache_keys_separate_tenant_property_year_and_month(self):
        fake_redis = FakeRedis()

        async def calculate(property_id, tenant_id, year, month):
            total = "2250.00" if tenant_id == "tenant-a" else "0.00"
            return {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "year": year,
                "month": month,
                "total": total,
                "currency": "USD",
                "count": 4 if tenant_id == "tenant-a" else 0,
            }

        with (
            patch.object(cache, "redis_client", fake_redis),
            patch(
                "app.services.reservations.calculate_total_revenue",
                new=AsyncMock(side_effect=calculate),
            ) as calculate_mock,
        ):
            tenant_a = await cache.get_revenue_summary(
                "prop-001", "tenant-a", 2024, 3
            )
            tenant_b = await cache.get_revenue_summary(
                "prop-001", "tenant-b", 2024, 3
            )
            tenant_a_cached = await cache.get_revenue_summary(
                "prop-001", "tenant-a", 2024, 3
            )

        self.assertEqual(tenant_a["total"], "2250.00")
        self.assertEqual(tenant_b["total"], "0.00")
        self.assertEqual(tenant_a_cached, tenant_a)
        self.assertEqual(calculate_mock.await_count, 2)
        self.assertEqual(
            [call[0] for call in fake_redis.setex_calls],
            [
                "revenue:tenant-a:prop-001:2024:3",
                "revenue:tenant-b:prop-001:2024:3",
            ],
        )
        self.assertEqual(json.loads(fake_redis.setex_calls[0][2]), tenant_a)

    async def test_cache_outage_falls_back_to_service_without_fabricating_data(self):
        fake_redis = FakeRedis()
        fake_redis.get_error = redis.ConnectionError("redis unavailable")
        expected = {
            "property_id": "prop-001",
            "tenant_id": "tenant-a",
            "year": 2024,
            "month": 3,
            "total": "2250.00",
            "currency": "USD",
            "count": 4,
        }

        with (
            patch.object(cache, "redis_client", fake_redis),
            patch(
                "app.services.reservations.calculate_total_revenue",
                new=AsyncMock(return_value=expected),
            ),
        ):
            result = await cache.get_revenue_summary(
                "prop-001", "tenant-a", 2024, 3
            )

        self.assertEqual(result, expected)


class DashboardApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_summary_preserves_exact_money_string(self):
        current_user = SimpleNamespace(tenant_id="tenant-a")
        summary = {
            "property_id": "prop-001",
            "tenant_id": "tenant-a",
            "year": 2024,
            "month": 3,
            "total": "2250.00",
            "currency": "USD",
            "count": 4,
        }

        with patch.object(
            dashboard, "get_revenue_summary", new=AsyncMock(return_value=summary)
        ) as get_summary:
            result = await dashboard.get_dashboard_summary(
                "prop-001", 2024, 3, current_user
            )

        get_summary.assert_awaited_once_with(
            "prop-001", "tenant-a", 2024, 3
        )
        self.assertEqual(result["total_revenue"], "2250.00")
        self.assertIsInstance(result["total_revenue"], str)

    async def test_cross_tenant_property_maps_to_safe_404(self):
        current_user = SimpleNamespace(tenant_id="tenant-a")

        with patch.object(
            dashboard,
            "get_revenue_summary",
            new=AsyncMock(side_effect=PropertyNotFoundError("prop-004")),
        ):
            with self.assertRaises(HTTPException) as raised:
                await dashboard.get_dashboard_summary(
                    "prop-004", 2024, 3, current_user
                )

        self.assertEqual(raised.exception.status_code, 404)
        self.assertEqual(raised.exception.detail, "Property not found")

    async def test_database_failure_maps_to_503_not_mock_summary(self):
        current_user = SimpleNamespace(tenant_id="tenant-a")

        with patch.object(
            dashboard,
            "get_revenue_summary",
            new=AsyncMock(side_effect=RevenueServiceError("database failed")),
        ):
            with self.assertRaises(HTTPException) as raised:
                await dashboard.get_dashboard_summary(
                    "prop-001", 2024, 3, current_user
                )

        self.assertEqual(raised.exception.status_code, 503)
        self.assertEqual(
            raised.exception.detail, "Revenue data is temporarily unavailable"
        )


if __name__ == "__main__":
    unittest.main()
