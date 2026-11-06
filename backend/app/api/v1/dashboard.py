from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any
from decimal import Decimal, ROUND_HALF_UP
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user),
    month: int | None = Query(default=None, ge=1, le=12),
    year: int | None = Query(default=None, ge=1, le=9998),
) -> Dict[str, Any]:
    
    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"
    
    if (month is None) != (year is None):
        raise HTTPException(status_code=422, detail="Month and year must be supplied together")
    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id, month, year)
    except Exception:
        raise HTTPException(status_code=503, detail="Revenue temporarily unavailable")
    
    # Sum at full precision, then round once for the two-decimal USD report.
    total_revenue = Decimal(revenue_data['total']).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if total_revenue == 0:
        total_revenue = abs(total_revenue)  # Avoid displaying negative zero.
    
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": format(total_revenue, ".2f"),
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
