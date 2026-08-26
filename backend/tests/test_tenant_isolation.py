import json
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.api.v1.dashboard import get_dashboard_summary
from app.core.tenant_resolver import TenantResolver
from app.models.auth import AuthenticatedUser
from app.services import cache


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None):
        self.values[key] = value


class TenantIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_revenue_cache_is_scoped_by_tenant(self):
        fake_redis = FakeRedis()

        async def calculate(property_id, tenant_id, month, year):
            total = "2250.000" if tenant_id == "tenant-a" else "900.000"
            return {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "month": month,
                "year": year,
                "total": total,
                "currency": "USD",
                "count": 4,
            }

        with (
            patch.object(cache, "redis_client", fake_redis),
            patch(
                "app.services.reservations.calculate_monthly_revenue",
                side_effect=calculate,
            ) as calculate_revenue,
        ):
            sunset = await cache.get_revenue_summary(
                "prop-001", "tenant-a", 3, 2024
            )
            ocean = await cache.get_revenue_summary(
                "prop-001", "tenant-b", 3, 2024
            )
            sunset_again = await cache.get_revenue_summary(
                "prop-001", "tenant-a", 3, 2024
            )

        self.assertEqual(sunset["total"], "2250.000")
        self.assertEqual(ocean["total"], "900.000")
        self.assertEqual(sunset_again["total"], "2250.000")
        self.assertEqual(calculate_revenue.await_count, 2)
        self.assertEqual(
            json.loads(
                fake_redis.values["revenue:tenant-a:prop-001:2024:03"]
            ),
            sunset,
        )
        self.assertEqual(
            json.loads(
                fake_redis.values["revenue:tenant-b:prop-001:2024:03"]
            ),
            ocean,
        )

    async def test_dashboard_rejects_user_without_tenant(self):
        user = AuthenticatedUser(
            id="user-without-tenant",
            email="missing-tenant@example.com",
            permissions=[],
            cities=[],
            is_admin=False,
            tenant_id=None,
        )

        with patch(
            "app.api.v1.dashboard.get_revenue_summary",
            new_callable=AsyncMock,
        ) as get_summary:
            with self.assertRaises(HTTPException) as error:
                await get_dashboard_summary("prop-001", 3, 2024, user)

        self.assertEqual(error.exception.status_code, 403)
        get_summary.assert_not_awaited()

    def test_tenant_resolver_uses_signed_app_metadata_only(self):
        tenant_id = TenantResolver.resolve_tenant_from_token(
            {
                "app_metadata": {"tenant_id": "tenant-a"},
                "user_metadata": {"tenant_id": "tenant-b"},
                "tenant_id": "tenant-b",
            }
        )

        self.assertEqual(tenant_id, "tenant-a")

    async def test_unknown_user_has_no_default_tenant(self):
        tenant_id = await TenantResolver.resolve_tenant_id(
            user_id="unknown-user",
            user_email="unknown@example.com",
            token_payload={"app_metadata": {}},
        )

        self.assertIsNone(tenant_id)


if __name__ == "__main__":
    unittest.main()
