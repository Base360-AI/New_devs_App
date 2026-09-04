from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any, List
from app.services.cache import get_revenue_summary
from app.services.reservations import list_tenant_properties, tenant_owns_property
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()


def resolve_tenant_id(current_user) -> str:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context is required",
        )
    return tenant_id


@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, str]]:
    tenant_id = resolve_tenant_id(current_user)
    return await list_tenant_properties(tenant_id)


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant_id = resolve_tenant_id(current_user)

    if not await tenant_owns_property(property_id, tenant_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found",
        )

    revenue_data = await get_revenue_summary(property_id, tenant_id)
    total_revenue_float = float(revenue_data["total"])

    return {
        "property_id": revenue_data["property_id"],
        "total_revenue": total_revenue_float,
        "currency": revenue_data["currency"],
        "reservations_count": revenue_data["count"],
    }
