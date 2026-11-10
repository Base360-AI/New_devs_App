import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import dashboard
from app.core.auth import authenticate_request
from app.models.auth import AuthenticatedUser
from app.services.reservations import MixedCurrencyError


def _user(tenant_id):
    return AuthenticatedUser(
        id="user-1",
        email="user@example.test",
        permissions=[],
        cities=[],
        is_admin=False,
        tenant_id=tenant_id,
    )


@pytest.fixture
def make_client():
    """Build a client for the dashboard router only (no app startup hooks)."""

    def _make(tenant_id):
        app = FastAPI()
        app.include_router(dashboard.router, prefix="/api/v1")
        app.dependency_overrides[authenticate_request] = lambda: _user(tenant_id)
        return TestClient(app)

    return _make


@pytest.fixture
def summary_calls(monkeypatch):
    calls = []

    async def fake_summary(property_id, tenant_id, month=None, year=None):
        calls.append((property_id, tenant_id, month, year))
        return {"property_id": property_id, "tenant_id": tenant_id, "total": "2250.00", "currency": "USD", "count": 4}

    monkeypatch.setattr(dashboard, "get_revenue_summary", fake_summary)
    return calls


def test_summary_uses_tenant_from_auth(make_client, summary_calls):
    response = make_client("tenant-a").get("/api/v1/dashboard/summary", params={"property_id": "prop-001"})

    assert response.status_code == 200
    assert summary_calls == [("prop-001", "tenant-a", None, None)]


def test_summary_ignores_simulated_tenant_header(make_client, summary_calls):
    response = make_client("tenant-a").get(
        "/api/v1/dashboard/summary",
        params={"property_id": "prop-001"},
        headers={"X-Simulated-Tenant": "tenant-b"},
    )

    assert response.status_code == 200
    assert summary_calls[0][1] == "tenant-a"


def test_summary_returns_cents_as_number_and_exact_string(make_client, summary_calls):
    body = make_client("tenant-a").get("/api/v1/dashboard/summary", params={"property_id": "prop-001"}).json()

    assert body == {
        "property_id": "prop-001",
        "total_revenue": 2250.0,
        "total_revenue_str": "2250.00",
        "currency": "USD",
        "reservations_count": 4,
    }


@pytest.mark.parametrize("tenant_id", [None, ""])
def test_summary_without_tenant_is_forbidden(make_client, summary_calls, tenant_id):
    # Regression: this used to fall back to a shared "default_tenant".
    response = make_client(tenant_id).get("/api/v1/dashboard/summary", params={"property_id": "prop-001"})

    assert response.status_code == 403
    assert summary_calls == []


def test_summary_passes_month_and_year(make_client, summary_calls):
    response = make_client("tenant-a").get(
        "/api/v1/dashboard/summary", params={"property_id": "prop-001", "month": 3, "year": 2024}
    )

    assert response.status_code == 200
    assert summary_calls == [("prop-001", "tenant-a", 3, 2024)]


@pytest.mark.parametrize(
    "params",
    [
        {"month": 3},
        {"year": 2024},
        {"month": 13, "year": 2024},
        {"month": 0, "year": 2024},
    ],
)
def test_summary_rejects_bad_period(make_client, summary_calls, params):
    response = make_client("tenant-a").get(
        "/api/v1/dashboard/summary", params={"property_id": "prop-001", **params}
    )

    assert response.status_code == 422
    assert summary_calls == []


def test_summary_returns_503_when_data_unavailable(make_client, monkeypatch):
    # Regression: DB errors used to be hidden behind hardcoded mock totals.
    async def failing_summary(*args, **kwargs):
        raise RuntimeError("database down")

    monkeypatch.setattr(dashboard, "get_revenue_summary", failing_summary)
    response = make_client("tenant-a").get("/api/v1/dashboard/summary", params={"property_id": "prop-001"})

    assert response.status_code == 503


def test_summary_returns_409_for_mixed_currencies(make_client, monkeypatch):
    async def mixed_summary(*args, **kwargs):
        raise MixedCurrencyError("prop-002 has reservations in 2 currencies")

    monkeypatch.setattr(dashboard, "get_revenue_summary", mixed_summary)
    response = make_client("tenant-a").get("/api/v1/dashboard/summary", params={"property_id": "prop-002"})

    assert response.status_code == 409


def test_properties_lists_only_callers_tenant(make_client, monkeypatch):
    seen = []

    async def fake_list(tenant_id):
        seen.append(tenant_id)
        return [{"id": "prop-004", "name": "Lakeside Cottage", "timezone": "America/New_York"}]

    monkeypatch.setattr(dashboard, "list_tenant_properties", fake_list)
    response = make_client("tenant-b").get("/api/v1/dashboard/properties")

    assert response.status_code == 200
    assert seen == ["tenant-b"]
    assert response.json()[0]["id"] == "prop-004"


def test_properties_without_tenant_is_forbidden(make_client, monkeypatch):
    async def fake_list(tenant_id):
        raise AssertionError("must not query without a tenant")

    monkeypatch.setattr(dashboard, "list_tenant_properties", fake_list)
    assert make_client(None).get("/api/v1/dashboard/properties").status_code == 403


def test_properties_returns_503_when_data_unavailable(make_client, monkeypatch):
    async def failing_list(tenant_id):
        raise RuntimeError("database down")

    monkeypatch.setattr(dashboard, "list_tenant_properties", failing_list)
    assert make_client("tenant-a").get("/api/v1/dashboard/properties").status_code == 503
