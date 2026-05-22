from decimal import Decimal, ROUND_HALF_UP
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:

    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"

    revenue_data = await get_revenue_summary(property_id, tenant_id)

    # Money must never round-trip through a binary float. total_amount is stored
    # as NUMERIC(10,3), so float(revenue_data['total']) introduces binary
    # representation error -- the "off by a few cents" the finance team saw, and
    # what trips the frontend's "Precision Mismatch" banner. Keep it Decimal,
    # round to whole cents once, and serialize as a string so the exact value
    # reaches the client.
    total_revenue = Decimal(revenue_data['total']).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": str(total_revenue),
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
