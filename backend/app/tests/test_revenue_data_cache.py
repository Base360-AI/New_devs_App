import pytest
from fastapi.testclient import TestClient

from app.services import cache as cache_service
from app.services import reservations

from app.main import app


@pytest.fixture
def client():
  with TestClient(app) as test_client:
      yield test_client


def login(client, email, password):
    response = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
    )
    response.raise_for_status()
    return response.json()["access_token"]


@pytest.fixture
def a_token(client):
    return login(
            client,
            "sunset@propertyflow.com",
            "client_a_2024"
    )


@pytest.fixture
def b_token(client):
    return login(
            client,
            "ocean@propertyflow.com",
            "client_b_2024"
    )


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def setex(self, key, ttl, value):
        self.values[key] = value


async def fake_revenue(property_id, tenant_id):
    totals = {
        "tenant-a": ("1000.00", 3),
        "tenant-b": ("2500.00", 5),
    }

    total, count = totals[tenant_id]

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": total,
        "currency": "USD",
        "count": count,
    }


def test_revenue_isolated_between_tenants(client, a_token, b_token, monkeypatch):
    monkeypatch.setattr(cache_service, "redis_client", FakeRedis())
    monkeypatch.setattr(reservations, "calculate_total_revenue", fake_revenue)

    response_a = client.get(
        "/api/v1/dashboard/summary?property_id=prop-001",
        headers={"Authorization": f"Bearer {a_token}"},
    )
    response_b = client.get(
        "/api/v1/dashboard/summary?property_id=prop-001",
        headers={"Authorization": f"Bearer {b_token}"},
    )

    assert response_a.status_code == 200
    assert response_b.status_code == 200
    assert response_a.json()["total_revenue"] == 1000.0
    assert response_b.json()["total_revenue"] == 2500.0
