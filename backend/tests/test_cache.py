import asyncio
import json

from redis.exceptions import ConnectionError as RedisConnectionError

from app.services import cache, reservations


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        assert ttl == 300
        self.values[key] = value


class FailingReadRedis(FakeRedis):
    async def get(self, key: str) -> str | None:
        raise RedisConnectionError("Redis is unavailable")


class FailingWriteRedis(FakeRedis):
    async def setex(self, key: str, ttl: int, value: str) -> None:
        raise RedisConnectionError("Redis is unavailable")


def test_revenue_cache_is_scoped_by_tenant(monkeypatch) -> None:
    fake_redis = FakeRedis()
    calculation_calls: list[tuple[str, str]] = []

    async def fake_calculate_total_revenue(
        property_id: str,
        tenant_id: str,
    ) -> dict:
        calculation_calls.append((property_id, tenant_id))
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": "100.00" if tenant_id == "tenant-a" else "200.00",
            "currency": "USD",
            "count": 1,
        }

    monkeypatch.setattr(cache, "redis_client", fake_redis)
    monkeypatch.setattr(
        reservations,
        "calculate_total_revenue",
        fake_calculate_total_revenue,
    )

    async def exercise_cache() -> tuple[dict, dict, dict]:
        tenant_a = await cache.get_revenue_summary("prop-001", "tenant-a")
        tenant_b = await cache.get_revenue_summary("prop-001", "tenant-b")
        tenant_a_cached = await cache.get_revenue_summary("prop-001", "tenant-a")
        return tenant_a, tenant_b, tenant_a_cached

    tenant_a, tenant_b, tenant_a_cached = asyncio.run(exercise_cache())

    assert tenant_a["total"] == "100.00"
    assert tenant_b["total"] == "200.00"
    assert tenant_a_cached == tenant_a
    assert calculation_calls == [
        ("prop-001", "tenant-a"),
        ("prop-001", "tenant-b"),
    ]
    assert set(fake_redis.values) == {
        "revenue:tenant-a:prop-001",
        "revenue:tenant-b:prop-001",
    }
    assert json.loads(fake_redis.values["revenue:tenant-a:prop-001"])[
        "tenant_id"
    ] == "tenant-a"


def test_cache_read_failure_falls_back_to_database(monkeypatch) -> None:
    expected = {
        "property_id": "prop-001",
        "tenant_id": "tenant-a",
        "total": "2250.00",
        "currency": "USD",
        "count": 4,
    }

    async def fake_calculate_total_revenue(
        property_id: str,
        tenant_id: str,
    ) -> dict:
        assert (property_id, tenant_id) == ("prop-001", "tenant-a")
        return expected

    monkeypatch.setattr(cache, "redis_client", FailingReadRedis())
    monkeypatch.setattr(
        reservations,
        "calculate_total_revenue",
        fake_calculate_total_revenue,
    )

    result = asyncio.run(cache.get_revenue_summary("prop-001", "tenant-a"))

    assert result == expected


def test_cache_write_failure_still_returns_database_result(monkeypatch) -> None:
    expected = {
        "property_id": "prop-001",
        "tenant_id": "tenant-a",
        "total": "2250.00",
        "currency": "USD",
        "count": 4,
    }

    async def fake_calculate_total_revenue(
        property_id: str,
        tenant_id: str,
    ) -> dict:
        return expected

    monkeypatch.setattr(cache, "redis_client", FailingWriteRedis())
    monkeypatch.setattr(
        reservations,
        "calculate_total_revenue",
        fake_calculate_total_revenue,
    )

    result = asyncio.run(cache.get_revenue_summary("prop-001", "tenant-a"))

    assert result == expected
