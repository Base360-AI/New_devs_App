from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Dict, Any, Optional
from app.services.cache import get_revenue_summary
from app.services.reservations import (
    calculate_monthly_revenue,
    list_tenant_properties,
    property_belongs_to_tenant,
)
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()


def _tenant_id(current_user) -> str:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tenant for this account")
    return tenant_id


@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    tenant_id = _tenant_id(current_user)
    try:
        return {"properties": await list_tenant_properties(tenant_id)}
    except Exception:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Data temporarily unavailable")


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    tenant_id = _tenant_id(current_user)

    # Only return data for a property this tenant actually owns.
    try:
        owned = await property_belongs_to_tenant(property_id, tenant_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Data temporarily unavailable")
    if not owned:
        # 404 rather than 403 so we don't confirm the id exists for another tenant.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")

    try:
        if month is not None and year is not None:
            revenue_data = await calculate_monthly_revenue(property_id, tenant_id, month, year)
        else:
            revenue_data = await get_revenue_summary(property_id, tenant_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Revenue data temporarily unavailable")

    response = {
        "property_id": revenue_data['property_id'],
        "total_revenue": revenue_data['total'],
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
    if month is not None and year is not None:
        response["month"] = month
        response["year"] = year
    return response
