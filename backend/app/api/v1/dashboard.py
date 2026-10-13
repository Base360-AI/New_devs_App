from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from decimal import Decimal
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

CURRENCY_EXPONENTS = {'USD': 2, 'EUR': 2, 'GBP': 2, 'JPY': 0, 'KWD': 3}

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:

    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"

    revenue_data = await get_revenue_summary(property_id, tenant_id)

    currency = revenue_data['currency']
    currency_exponent = CURRENCY_EXPONENTS.get(currency, 2)
    total_decimal = Decimal(str(revenue_data['total']))
    amount_minor_units = int(total_decimal * (10 ** currency_exponent))

    return {
        "property_id": revenue_data['property_id'],
        "amount_minor_units": amount_minor_units,
        "currency": currency,
        "currency_exponent": currency_exponent,
        "reservations_count": revenue_data['count']
    }
