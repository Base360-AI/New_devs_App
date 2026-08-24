from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user
from decimal import Decimal, ROUND_HALF_UP

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(
            status_code=403,
            detail="Tenant context is required",
        )
    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id)
    except Exception as e:
        raise HTTPException(status_code=503, detail=str("Revenue data temporarily unavailable")) from e
    
    total_revenue = revenue_data["total"]

    reported_total = total_revenue.quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": format(reported_total, ".2f"),
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
