import json

import pytest

from app.services import cache
from app.services import reservations


def _result(property_id, tenant_id, total, count):
    return {"property_id": property_id, "tenant_id": tenant_id, "total": total, "currency": "USD", "count": count}


@pytest.fixture
def calc_calls(monkeypatch):
    """Replace the DB-backed calculators with fakes that record their calls."""
    calls = []
    totals = {("tenant-a", "prop-001"): "2250.00", ("tenant-b", "prop-001"): "0.00"}

    async def fake_total(property_id, tenant_id):
        calls.append(("total", tenant_id, property_id))
        return _result(property_id, tenant_id, totals.get((tenant_id, property_id), "0.00"), 0)

    async def fake_monthly(property_id, tenant_id, month, year):
        calls.append(("monthly", tenant_id, property_id, month, year))
        return _result(property_id, tenant_id, "123.45", 1)

    monkeypatch.setattr(reservations, "calculate_total_revenue", fake_total)
    monkeypatch.setattr(reservations, "calculate_monthly_revenue", fake_monthly)
    return calls


@pytest.mark.asyncio
async def test_same_property_id_is_cached_per_tenant(fake_redis, calc_calls):
    # Regression: the key was revenue:{property_id}, so tenant-b got tenant-a's
    # cached prop-001 total.
    a = await cache.get_revenue_summary("prop-001", "tenant-a")
    b = await cache.get_revenue_summary("prop-001", "tenant-b")

    assert a["total"] == "2250.00"
    assert b["total"] == "0.00"
    assert set(fake_redis.store) == {
        "revenue:tenant-a:prop-001:all",
        "revenue:tenant-b:prop-001:all",
    }
    assert len(calc_calls) == 2


@pytest.mark.asyncio
async def test_cache_hit_returns_cached_value_without_recalculating(fake_redis, calc_calls):
    await cache.get_revenue_summary("prop-001", "tenant-a")
    again = await cache.get_revenue_summary("prop-001", "tenant-a")

    assert again["total"] == "2250.00"
    assert len(calc_calls) == 1
    assert fake_redis.ttls["revenue:tenant-a:prop-001:all"] == 300


@pytest.mark.asyncio
async def test_cached_entry_of_other_tenant_is_never_returned(fake_redis, calc_calls):
    fake_redis.store["revenue:tenant-a:prop-001:all"] = json.dumps(_result("prop-001", "tenant-a", "2250.00", 4))

    b = await cache.get_revenue_summary("prop-001", "tenant-b")

    assert b["tenant_id"] == "tenant-b"
    assert b["total"] == "0.00"


@pytest.mark.asyncio
async def test_monthly_and_all_time_use_separate_keys(fake_redis, calc_calls):
    await cache.get_revenue_summary("prop-001", "tenant-a")
    monthly = await cache.get_revenue_summary("prop-001", "tenant-a", month=3, year=2024)

    assert monthly["total"] == "123.45"
    assert "revenue:tenant-a:prop-001:2024-03" in fake_redis.store
    assert calc_calls[-1] == ("monthly", "tenant-a", "prop-001", 3, 2024)


@pytest.mark.asyncio
@pytest.mark.parametrize("tenant_id", ["", None])
async def test_missing_tenant_is_rejected(fake_redis, calc_calls, tenant_id):
    with pytest.raises(ValueError):
        await cache.get_revenue_summary("prop-001", tenant_id)
    assert fake_redis.store == {}
    assert calc_calls == []
