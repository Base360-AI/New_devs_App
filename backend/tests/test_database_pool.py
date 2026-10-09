import pytest
from app.core.database_pool import DatabasePool


@pytest.mark.asyncio
async def test_pool_initializes_from_database_url_and_runs_queries():
    pool = DatabasePool()
    await pool.initialize()
    try:
        assert pool.pool is not None
        async with pool.get_session() as conn:
            assert await conn.fetchval("SELECT COUNT(*) FROM tenants") == 2
    finally:
        await pool.close()
