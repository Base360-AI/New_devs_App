from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any
from app.services.cache import get_revenue_summary
from app.services.reservations import get_tenant_properties
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()


def _tenant_id_for(current_user: Any) -> str:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Missing tenant context")
    return tenant_id


@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: Any = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant_id = _tenant_id_for(current_user)
    properties = await get_tenant_properties(tenant_id)
    return {
        "properties": properties,
        "is_fallback": any(prop.get("is_fallback") for prop in properties),
    }

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: int = Query(3, ge=1, le=12),
    year: int = Query(2024, ge=2000, le=2100),
    current_user: Any = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant_id = _tenant_id_for(current_user)
    
    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id, month, year)
    except LookupError:
        raise HTTPException(status_code=404, detail="Property not found")
    
    return {
        "property_id": revenue_data["property_id"],
        "property_name": revenue_data["property_name"],
        "property_timezone": revenue_data["property_timezone"],
        "reporting_period": revenue_data["reporting_period"],
        "total_revenue": revenue_data["total"],
        "currency": revenue_data["currency"],
        "reservations_count": revenue_data["count"],
        "is_fallback": revenue_data.get("is_fallback", False),
        "fallback_reason": revenue_data.get("fallback_reason"),
    }
