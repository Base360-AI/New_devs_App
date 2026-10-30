import asyncio
import logging
import os
from unittest.mock import patch

import redis.asyncio as redis

from app.services import cache


KEYS = ["revenue:prop-001", "revenue:tenant-a:prop-001", "revenue:tenant-b:prop-001"]


def test_cached_revenue_is_not_shared_between_tenants():
    async def run():
        client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        try:
            await client.delete(*KEYS)
            with patch.object(cache, "redis_client", client):
                a = await cache.get_revenue_summary("prop-001", "tenant-a")
                b = await cache.get_revenue_summary("prop-001", "tenant-b")
            await client.delete(*KEYS)
            return a, b
        finally:
            await client.aclose()

    a, b = asyncio.run(run())
    assert a["total"] == "2250.000" and a["count"] == 4
    assert b["total"] == "0.00" and b["count"] == 0


def test_cache_miss_then_hit_is_logged_with_tenant_key(caplog):
    async def run():
        client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        try:
            await client.delete(*KEYS)
            with patch.object(cache, "redis_client", client):
                await cache.get_revenue_summary("prop-001", "tenant-a")
                await cache.get_revenue_summary("prop-001", "tenant-a")
            await client.delete(*KEYS)
        finally:
            await client.aclose()

    with caplog.at_level(logging.INFO, logger="app.services.cache"):
        asyncio.run(run())

    messages = [r.getMessage() for r in caplog.records if r.name == "app.services.cache"]
    assert messages == [
        "REVENUE_CACHE MISS key=revenue:tenant-a:prop-001 tenant=tenant-a property=prop-001",
        "REVENUE_CACHE HIT key=revenue:tenant-a:prop-001 tenant=tenant-a property=prop-001",
    ]
