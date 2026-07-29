from fastapi import APIRouter, Depends, Query
from typing import Dict, Any
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    currency: str = Query("USD", pattern=r"^[A-Za-z]{3}$"),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    
    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"
    
    normalized_currency = currency.upper()
    revenue_data = await get_revenue_summary(
        property_id,
        tenant_id,
        month,
        normalized_currency,
    )
    
    total_revenue_float = float(revenue_data['total'])
    
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": total_revenue_float,
        "currency": revenue_data['currency'],
        "month": revenue_data['month'],
        "reservations_count": revenue_data['count']
    }
