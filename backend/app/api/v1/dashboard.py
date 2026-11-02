from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Dict, Any
from app.services.cache import get_revenue_summary
from app.services.reservations import calculate_monthly_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: int | None = Query(default=None, ge=1, le=12),
    year: int | None = Query(default=None, ge=2000, le=2100),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant context is required")

    if (month is None) != (year is None):
        raise HTTPException(status_code=400, detail="month and year must be provided together")

    try:
        if month is not None and year is not None:
            revenue_data = await calculate_monthly_summary(property_id, month, year, tenant_id)
            revenue_data.update({"property_id": property_id, "tenant_id": tenant_id, "currency": "USD"})
        else:
            revenue_data = await get_revenue_summary(property_id, tenant_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Revenue data is temporarily unavailable",
        ) from exc
    
    total_revenue_float = float(revenue_data['total'])
    
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": total_revenue_float,
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
