from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Dict, Any, Optional, List
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user
from app.models.auth import AuthenticatedUser
from app.services.reservations import list_properties
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

def _require_tenant(current_user: Any) -> str:
    """Ensure user belongs to a tenant; 403 Forbidden otherwise."""
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        logger.warning(f"Dashboard access denied - no tenant for user {getattr(current_user, 'email', 'unknown')}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tenant associated with this account"
        )
    return tenant_id

@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: Any = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Properties belonging to the caller's tenant (drives the dashboard selector)."""
    tenant_id = _require_tenant(current_user)
    try:
        return await list_properties(tenant_id)
    except Exception as e:
        logger.exception(f"Failed to list properties for tenant {tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Property data temporarily unavailable"
        )

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = Query(None, ge=1, le=12, description="Calendar month (1-12)"),
    year: Optional[int] = Query(None, ge=2000, le=2100, description="Year (e.g. 2024)"),
    current_user: Any = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant_id = _require_tenant(current_user)

    if (month is None) != (year is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="month and year must be provided together"
        )

    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id, month=month, year=year)
    except Exception as e:
        logger.exception(f"Revenue lookup failed for tenant={tenant_id} property={property_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Revenue data temporarily unavailable"
        )

    if revenue_data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found"
        )

    return {
        "property_id": revenue_data["property_id"],
        "property_name": revenue_data.get("property_name"),
        "timezone": revenue_data.get("timezone"),
        "total_revenue": revenue_data["total"],
        "currency": revenue_data["currency"],
        "reservations_count": revenue_data["count"],
        "period": {"month": month, "year": year} if month is not None else None,
    }
