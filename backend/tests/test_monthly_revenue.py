import asyncio
from decimal import Decimal

from app.core.database_pool import DatabasePool
from app.services.reservations import calculate_monthly_revenue


def monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Decimal:
    async def run():
        pool = DatabasePool()
        await pool.initialize()
        try:
            async with pool.get_session() as session:
                return await calculate_monthly_revenue(property_id, tenant_id, month, year, db_session=session)
        finally:
            await pool.close()

    return asyncio.run(run())


def test_march_uses_property_timezone():
    # res-tz-1 checks in 2024-02-29 23:30 UTC = 2024-03-01 00:30 Europe/Paris
    assert monthly_revenue("prop-001", "tenant-a", 3, 2024) == Decimal("2250.000")


def test_february_excludes_booking_that_is_march_in_local_time():
    assert monthly_revenue("prop-001", "tenant-a", 2, 2024) == Decimal("0")


def test_same_property_id_in_other_tenant_is_not_counted():
    assert monthly_revenue("prop-001", "tenant-b", 3, 2024) == Decimal("0")


def test_new_york_property_march_total():
    assert monthly_revenue("prop-004", "tenant-b", 3, 2024) == Decimal("1776.500")
