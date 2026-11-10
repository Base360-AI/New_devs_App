import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: needs the seeded Postgres from docker-compose (skipped when unreachable)",
    )


class FakeRedis:
    """In-memory stand-in for the async Redis client used by the revenue cache."""

    def __init__(self):
        self.store = {}
        self.ttls = {}

    async def get(self, key):
        return self.store.get(key)

    async def setex(self, key, ttl, value):
        self.store[key] = value
        self.ttls[key] = ttl


@pytest.fixture
def fake_redis(monkeypatch):
    from app.services import cache

    fake = FakeRedis()
    monkeypatch.setattr(cache, "redis_client", fake)
    return fake
