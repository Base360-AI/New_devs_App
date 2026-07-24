import asyncio
import os
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from supabase import create_client

from app.config import settings
from app.main import app
from app.services.reservations import calculate_monthly_revenue


@pytest.fixture
def client():
  with TestClient(app) as test_client:
      yield test_client


@pytest.fixture
def a_token():
    supabase = create_client(
        settings.supabase_url,
        settings.supabase_anon_key,
    )
    response = supabase.auth.sign_in_with_password({
        "email": "sunset@propertyflow.com",
        "password": os.environ["TEST_TENANT_A_PASSWORD"],
    })
    return response.session.access_token


def test_monthly_revenue_endpoint_counts_march_in_property_timezone(client, a_token):
    # prop-001 is Europe/Paris. The res-tz-1 reservation starts at
    # 2024-02-29 23:30 UTC, which is 2024-03-01 00:30 local time.
    response = client.get(
        "/api/v1/revenue/2024/3/?property_id=prop-001",
        headers={"Authorization": f"Bearer {a_token}"},
    )
    assert response.status_code == 200
    assert response.json()["total_revenue"] == 3500.0


def test_monthly_revenue_rounds_half_cents_after_aggregation():
    class Result:
        def __init__(self, *, scalar=None, row=None):
            self.scalar = scalar
            self.row = row

        def scalar_one_or_none(self):
            return self.scalar

        def fetchone(self):
            return self.row

    class Session:
        def __init__(self):
            self.results = iter([
                Result(scalar="UTC"),
                Result(row=SimpleNamespace(total=Decimal("10.005"))),
            ])

        async def execute(self, _query, _parameters):
            return next(self.results)

    total = asyncio.run(calculate_monthly_revenue(
        property_id="prop-001",
        month=3,
        year=2024,
        db_session=Session(),
        tenant_id="tenant-a",
    ))

    assert total == Decimal("10.01")
