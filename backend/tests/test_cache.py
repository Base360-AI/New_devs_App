import pytest
from app.services.cache import get_revenue_summary


@pytest.mark.asyncio
async def test_cached_revenue_is_isolated_per_tenant_for_same_property_id(fake_redis):
    tenant_a = await get_revenue_summary("prop-001", "tenant-a")
    tenant_b = await get_revenue_summary("prop-001", "tenant-b")

    assert tenant_a["tenant_id"] == "tenant-a"
    assert tenant_b["tenant_id"] == "tenant-b"
    assert tenant_b["count"] == 0
