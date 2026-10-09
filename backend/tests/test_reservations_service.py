from decimal import Decimal

import pytest

from app.core import database_pool
from app.core.database_pool import DatabasePool
from app.services import reservations


@pytest.mark.asyncio
async def test_database_failure_surfaces_instead_of_returning_mock_data(monkeypatch):
    unreachable = DatabasePool()
    monkeypatch.setattr(database_pool.settings, "database_url", "postgresql://x:x@127.0.0.1:1/none")
    monkeypatch.setattr(reservations, "db_pool", unreachable, raising=False)

    with pytest.raises(Exception):
        await reservations.calculate_total_revenue("prop-001", "tenant-a")


@pytest.mark.asyncio
async def test_month_bounds_use_property_timezone():
    # res-tz-1 checks in 2024-02-29 23:30 UTC = 2024-03-01 00:30 in Europe/Paris.
    march = await reservations.calculate_monthly_revenue("prop-001", "tenant-a", 3, 2024)
    february = await reservations.calculate_monthly_revenue("prop-001", "tenant-a", 2, 2024)

    assert march == Decimal("2250.00")
    assert february == Decimal("0.00")


@pytest.mark.asyncio
async def test_total_is_quantized_to_two_decimals():
    result = await reservations.calculate_total_revenue("prop-001", "tenant-a")

    assert result["total"] == "2250.00"


@pytest.mark.asyncio
async def test_total_rounds_half_up_once_at_the_end(extra_reservation):
    # prop-005 seed total is 3256.000; adding 0.005 gives exactly 3256.005 -> 3256.01
    await extra_reservation("res-half-up", "prop-005", "tenant-b", "0.005")

    result = await reservations.calculate_total_revenue("prop-005", "tenant-b")

    assert result["total"] == "3256.01"
