"""
Integration tests against the seeded Postgres from docker-compose
(database/schema.sql + database/seed.sql). Skipped when the DB is unreachable.

Run inside the backend container:
    docker compose exec backend pytest -m integration
"""
import pytest
import pytest_asyncio

from app.core.database_pool import db_pool
from app.services.reservations import (
    calculate_monthly_revenue,
    calculate_total_revenue,
    list_tenant_properties,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture(autouse=True)
async def fresh_pool():
    """
    The pool is process-wide, but each test runs in its own event loop and
    asyncpg connections cannot move between loops. Start and end every test
    with a fresh engine.
    """
    await _reset_pool()
    await db_pool.initialize()
    try:
        async with db_pool.get_session() as session:
            from sqlalchemy import text

            await session.execute(text("SELECT 1"))
    except Exception as e:  # pragma: no cover - environment dependent
        await _reset_pool()
        pytest.skip(f"Postgres not reachable: {e}")
    yield
    await _reset_pool()


async def _reset_pool():
    if db_pool.engine:
        await db_pool.engine.dispose()
    db_pool.engine = None
    db_pool.session_factory = None


async def test_all_time_total_uses_real_data_not_mock():
    # Mock fallback used to return 1000.00 / 3 for prop-001.
    result = await calculate_total_revenue("prop-001", "tenant-a")
    assert result["total"] == "2250.00"
    assert result["count"] == 4


async def test_same_property_id_is_isolated_per_tenant():
    a = await calculate_total_revenue("prop-001", "tenant-a")
    b = await calculate_total_revenue("prop-001", "tenant-b")
    assert a["total"] == "2250.00"
    assert b["total"] == "0.00"
    assert b["count"] == 0


async def test_tenant_cannot_read_other_tenants_property():
    result = await calculate_total_revenue("prop-004", "tenant-a")
    assert result["total"] == "0.00"
    assert result["count"] == 0


@pytest.mark.parametrize(
    "property_id, tenant_id, total, count",
    [
        ("prop-001", "tenant-a", "2250.00", 4),
        ("prop-002", "tenant-a", "4975.50", 4),
        ("prop-003", "tenant-a", "6100.50", 2),
        ("prop-004", "tenant-b", "1776.50", 4),
        ("prop-005", "tenant-b", "3256.00", 3),
        ("prop-001", "tenant-b", "0.00", 0),
    ],
)
async def test_march_2024_totals_per_property(property_id, tenant_id, total, count):
    result = await calculate_monthly_revenue(property_id, tenant_id, 3, 2024)
    assert (result["total"], result["count"]) == (total, count)


async def test_booking_late_on_feb_29_utc_counts_as_march_in_paris():
    # res-tz-1: 2024-02-29 23:30 UTC == 2024-03-01 00:30 Europe/Paris.
    # A UTC month boundary gives March = 1000.00 / 3 and February = 1250.00 / 1.
    march = await calculate_monthly_revenue("prop-001", "tenant-a", 3, 2024)
    february = await calculate_monthly_revenue("prop-001", "tenant-a", 2, 2024)

    assert (march["total"], march["count"]) == ("2250.00", 4)
    assert (february["total"], february["count"]) == ("0.00", 0)


async def test_december_rolls_over_to_next_year():
    result = await calculate_monthly_revenue("prop-001", "tenant-a", 12, 2023)
    assert (result["total"], result["count"]) == ("0.00", 0)


async def test_totals_always_have_two_decimals():
    for property_id, tenant_id in [("prop-001", "tenant-a"), ("prop-004", "tenant-b")]:
        result = await calculate_total_revenue(property_id, tenant_id)
        assert len(result["total"].split(".")[1]) == 2


@pytest.mark.parametrize(
    "tenant_id, expected",
    [
        ("tenant-a", [("prop-001", "Beach House Alpha"), ("prop-002", "City Apartment Downtown"), ("prop-003", "Country Villa Estate")]),
        ("tenant-b", [("prop-001", "Mountain Lodge Beta"), ("prop-004", "Lakeside Cottage"), ("prop-005", "Urban Loft Modern")]),
        ("tenant-unknown", []),
    ],
)
async def test_property_list_is_scoped_to_tenant(tenant_id, expected):
    properties = await list_tenant_properties(tenant_id)
    assert [(p["id"], p["name"]) for p in properties] == expected
