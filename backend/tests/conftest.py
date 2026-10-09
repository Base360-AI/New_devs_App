"""Shared test configuration.

DB-backed tests run against a real Postgres loaded with database/schema.sql and
database/seed.sql. Point TEST_DATABASE_URL at it (default: localhost:5544, see
README of the test run command in the task notes).
"""
import os
from datetime import datetime, timezone

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5544/propertyflow"
)
# Must be set before any `app.*` import reads settings.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import fakeredis
import pytest_asyncio

from app.core.database_pool import db_pool


@pytest_asyncio.fixture
async def fake_redis(monkeypatch):
    from app.services import cache

    client = fakeredis.FakeAsyncRedis()
    monkeypatch.setattr(cache, "redis_client", client)
    yield client
    await client.aclose()


@pytest_asyncio.fixture(autouse=True)
async def reset_db_pool():
    """Each test runs on its own event loop, so drop the shared pool after it."""
    yield
    await db_pool.close()
    db_pool.pool = None


@pytest_asyncio.fixture
async def extra_reservation():
    """Insert a reservation for the test and delete it afterwards."""
    inserted = []

    async def _insert(res_id, property_id, tenant_id, amount, currency="USD", check_in=datetime(2024, 3, 10, 12, tzinfo=timezone.utc)):
        if db_pool.pool is None:
            await db_pool.initialize()
        async with db_pool.get_session() as conn:
            await conn.execute(
                "INSERT INTO reservations (id, property_id, tenant_id, check_in_date, check_out_date,"
                " total_amount, currency) VALUES ($1, $2, $3, $4::timestamptz, $4::timestamptz + interval '2 days',"
                " $5::numeric, $6)",
                res_id, property_id, tenant_id, check_in, amount, currency,
            )
        inserted.append(res_id)

    yield _insert

    if inserted:
        if db_pool.pool is None:
            await db_pool.initialize()
        async with db_pool.get_session() as conn:
            await conn.execute("DELETE FROM reservations WHERE id = ANY($1::text[])", inserted)
