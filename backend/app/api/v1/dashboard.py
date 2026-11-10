from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, Optional
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user
from app.models.auth import AuthenticatedUser

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = Query(None, ge=1, le=12, description="Calendar month in the property's timezone"),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    current_user: AuthenticatedUser = Depends(get_current_user)
) -> Dict[str, Any]:

    if (month is None) != (year is None):
        raise HTTPException(status_code=422, detail="month and year must be given together")

    # A user without a tenant must not fall into a shared bucket that other
    # tenant-less users could read; refuse instead.
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant associated with this account")

    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id, month, year)
    except Exception:
        raise HTTPException(status_code=503, detail="Revenue data temporarily unavailable")

    total_revenue_float = float(revenue_data['total'])
    
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": total_revenue_float,
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
