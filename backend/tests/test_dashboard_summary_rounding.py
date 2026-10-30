import types

import pytest
from fastapi.testclient import TestClient

from app.core.auth import authenticate_request
from app.main import app


def get_summary(total: str):
    async def fake_get_revenue_summary(property_id, tenant_id):
        return {
            "property_id": "prop-002",
            "tenant_id": "tenant-a",
            "total": total,
            "currency": "USD",
            "count": 5,
        }

    app.dependency_overrides[authenticate_request] = lambda: types.SimpleNamespace(
        tenant_id="tenant-a"
    )
    try:
        import app.api.v1.dashboard as dashboard

        original = dashboard.get_revenue_summary
        dashboard.get_revenue_summary = fake_get_revenue_summary
        try:
            return TestClient(app).get("/api/v1/dashboard/summary?property_id=prop-002")
        finally:
            dashboard.get_revenue_summary = original
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "total, expected",
    [
        ("5095.565", 5095.57),
        ("2250.055", 2250.06),
        ("1.005", 1.01),
        ("2250.000", 2250.0),
        ("4975.5", 4975.5),
        ("0.00", 0.0),
    ],
)
def test_total_revenue_is_rounded_half_up_to_two_decimals(total, expected):
    response = get_summary(total)
    assert response.status_code == 200
    value = response.json()["total_revenue"]
    assert isinstance(value, (int, float)) and not isinstance(value, bool)
    assert value == expected
