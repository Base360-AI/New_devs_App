from datetime import timezone
from decimal import Decimal

import pytest

from app.api.v1 import dashboard
from app.services import reservations


def test_paris_march_bounds_include_late_february_utc_checkin():
    start, end = reservations.month_bounds_utc(2024, 3, "Europe/Paris")

    assert start.isoformat() == "2024-02-29T23:00:00+00:00"
    assert end.isoformat() == "2024-03-31T22:00:00+00:00"
    assert start.tzinfo == timezone.utc


def test_money_format_returns_decimal_string():
    assert reservations.format_money(Decimal("1000.000")) == "1000.00"
    assert reservations.format_money(Decimal("10.005")) == "10.01"


@pytest.mark.asyncio
async def test_tenant_aware_fallback_does_not_cross_property_metadata(monkeypatch):
    async def fail_pool():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(reservations, "_ensure_pool", fail_pool)

    tenant_a = await reservations.calculate_monthly_revenue("prop-001", "tenant-a", 3, 2024)
    tenant_b = await reservations.calculate_monthly_revenue("prop-001", "tenant-b", 3, 2024)

    assert tenant_a["property_name"] == "Beach House Alpha"
    assert tenant_b["property_name"] == "Mountain Lodge Beta"
    assert tenant_a["tenant_id"] == "tenant-a"
    assert tenant_b["tenant_id"] == "tenant-b"
    assert tenant_a["is_fallback"] is True
    assert tenant_b["is_fallback"] is True


@pytest.mark.asyncio
async def test_tenant_aware_fallback_rejects_other_tenant_property(monkeypatch):
    async def fail_pool():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(reservations, "_ensure_pool", fail_pool)

    with pytest.raises(LookupError):
        await reservations.calculate_monthly_revenue("prop-004", "tenant-a", 3, 2024)


@pytest.mark.asyncio
async def test_dashboard_summary_returns_decimal_string(monkeypatch):
    class User:
        tenant_id = "tenant-a"

    async def fake_revenue_summary(property_id, tenant_id, month, year):
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "property_name": "Beach House Alpha",
            "property_timezone": "Europe/Paris",
            "reporting_period": {"month": month, "year": year, "label": "March 2024"},
            "total": "2250.00",
            "currency": "USD",
            "count": 4,
            "is_fallback": False,
        }

    monkeypatch.setattr(dashboard, "get_revenue_summary", fake_revenue_summary)

    response = await dashboard.get_dashboard_summary("prop-001", 3, 2024, User())

    assert response["total_revenue"] == "2250.00"
    assert isinstance(response["total_revenue"], str)
