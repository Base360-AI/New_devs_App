import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.api.v1 import dashboard
from app.core.auth import authenticate_request
from app.models.auth import AuthenticatedUser


def make_app(tenant_id):
    app = FastAPI()
    app.include_router(dashboard.router, prefix="/api/v1")
    user = AuthenticatedUser(
        id="u1", email="u@x.com", permissions=[], cities=[], is_admin=False, tenant_id=tenant_id
    )
    app.dependency_overrides[authenticate_request] = lambda: user
    return app


def make_client(tenant_id):
    return TestClient(make_app(tenant_id))


@pytest.mark.parametrize("tenant_id", [None, ""])
def test_summary_rejects_user_without_tenant(tenant_id):
    client = make_client(tenant_id)

    response = client.get("/api/v1/dashboard/summary", params={"property_id": "prop-001"})

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_summary_returns_total_revenue_as_number(fake_redis):
    app = make_app("tenant-a")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        body = (await client.get("/api/v1/dashboard/summary", params={"property_id": "prop-001"})).json()

    assert body["total_revenue"] == 2250.0
