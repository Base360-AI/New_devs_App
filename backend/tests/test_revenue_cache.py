from app.services.cache import build_revenue_cache_key


def test_revenue_cache_key_includes_tenant_property_and_period():
    tenant_a_key = build_revenue_cache_key("prop-001", "tenant-a", 3, 2024)
    tenant_b_key = build_revenue_cache_key("prop-001", "tenant-b", 3, 2024)
    april_key = build_revenue_cache_key("prop-001", "tenant-a", 4, 2024)

    assert tenant_a_key == "revenue:tenant-a:prop-001:2024:03"
    assert tenant_b_key == "revenue:tenant-b:prop-001:2024:03"
    assert tenant_a_key != tenant_b_key
    assert tenant_a_key != april_key
