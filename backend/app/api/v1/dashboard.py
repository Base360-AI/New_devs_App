from decimal import Decimal, ROUND_HALF_UP
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, Optional
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:

    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"

    revenue_data = await get_revenue_summary(property_id, tenant_id, month, year)

    # Money must not travel as float: IEEE-754 cannot exactly represent
    # values like 0.1, so float() introduces precision drift that
    # accumulates in any downstream arithmetic. Quantize to 2 decimals
    # (USD) using Decimal and serialize as a string so the API contract
    # carries the exact value (industry pattern: Stripe, PayPal, etc.).
    total_revenue = Decimal(revenue_data['total']).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )

    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": str(total_revenue),
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
