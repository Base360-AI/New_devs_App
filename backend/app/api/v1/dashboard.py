from fastapi import APIRouter, Depends, Query
from typing import Any, Dict, List
from app.services.cache import get_revenue_summary
from app.services.properties import list_tenant_properties
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()


@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"
    return await list_tenant_properties(tenant_id)

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: int = Query(3, ge=1, le=12),
    year: int = Query(2024, ge=1),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    
    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"
    
    revenue_data = await get_revenue_summary(property_id, tenant_id, month, year)
    
    return {
        "property_id": revenue_data["property_id"],
        "month": revenue_data["month"],
        "year": revenue_data["year"],
        "total_revenue": revenue_data["total"],
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
