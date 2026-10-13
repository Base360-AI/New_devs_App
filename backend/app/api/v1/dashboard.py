from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any, Dict, List, Optional
from app.services.cache import get_revenue_summary
from app.services.reservations import (
    MixedCurrencyError,
    PropertyNotFoundError,
    RevenueUnavailableError,
    list_properties,
)
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

def _require_tenant(current_user) -> str:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="User is not assigned to a tenant")
    return tenant_id


@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: dict = Depends(get_current_user)
) -> List[Dict[str, str]]:
    tenant_id = _require_tenant(current_user)
    try:
        return await list_properties(tenant_id)
    except RevenueUnavailableError:
        raise HTTPException(status_code=503, detail="Property list is temporarily unavailable")


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    year: Optional[int] = Query(None, ge=2000, le=2100),
    month: Optional[int] = Query(None, ge=1, le=12),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:

    tenant_id = _require_tenant(current_user)

    if (year is None) != (month is None):
        raise HTTPException(status_code=422, detail="year and month must be provided together")

    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id, year, month)
    except PropertyNotFoundError:
        # Same response whether the property doesn't exist or belongs to another tenant
        raise HTTPException(status_code=404, detail="Property not found")
    except MixedCurrencyError:
        raise HTTPException(status_code=409, detail="Reservations use more than one currency")
    except RevenueUnavailableError:
        raise HTTPException(status_code=503, detail="Revenue data is temporarily unavailable")

    return {
        "property_id": revenue_data['property_id'],
        # Decimal string rounded to cents, e.g. "2250.00" (never a float)
        "total_revenue": revenue_data['total'],
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
