import asyncio
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.reservations import round_currency_amount
from app.api.v1 import dashboard


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        ("1.004", "1.00"),
        ("1.005", "1.01"),
        ("1.006", "1.01"),
        ("-1.005", "-1.01"),
        ("2250.000", "2250.00"),
        ("4975.500", "4975.50"),
        ("0", "0.00"),
    ],
)
def test_round_currency_amount_uses_half_up_rounding(
    amount: str,
    expected: str,
) -> None:
    assert round_currency_amount(Decimal(amount)) == expected


def test_round_currency_amount_returns_a_two_decimal_string() -> None:
    result = round_currency_amount(Decimal("10"))

    assert result == "10.00"
    assert isinstance(result, str)


def test_dashboard_preserves_the_finalized_decimal_string(monkeypatch) -> None:
    async def fake_revenue_summary(property_id: str, tenant_id: str) -> dict:
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": "1.01",
            "currency": "USD",
            "count": 1,
        }

    monkeypatch.setattr(dashboard, "get_revenue_summary", fake_revenue_summary)

    result = asyncio.run(
        dashboard.get_dashboard_summary(
            property_id="prop-001",
            current_user=SimpleNamespace(tenant_id="tenant-a"),
        )
    )

    assert result["total_revenue"] == "1.01"
    assert isinstance(result["total_revenue"], str)
