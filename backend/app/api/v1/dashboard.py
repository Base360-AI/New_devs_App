from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import authenticate_request as get_current_user
from app.services.cache import get_revenue_summary
from app.services.reservations import (
    PropertyNotFoundError,
    RevenueServiceError,
    get_properties_for_tenant,
)

router = APIRouter()


def _tenant_id(current_user: Any) -> str:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant access is unavailable",
        )
    return tenant_id


@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: Any = Depends(get_current_user),
) -> List[Dict[str, str]]:
    try:
        return await get_properties_for_tenant(_tenant_id(current_user))
    except RevenueServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Property data is temporarily unavailable",
        ) from exc


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    year: int = Query(default=2024, ge=1, le=9999),
    month: int = Query(default=3, ge=1, le=12),
    current_user: Any = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        revenue_data = await get_revenue_summary(
            property_id, _tenant_id(current_user), year, month
        )
    except PropertyNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Property not found",
        ) from exc
    except RevenueServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Revenue data is temporarily unavailable",
        ) from exc

    return {
        "property_id": revenue_data["property_id"],
        "year": revenue_data["year"],
        "month": revenue_data["month"],
        "total_revenue": revenue_data["total"],
        "currency": revenue_data["currency"],
        "reservations_count": revenue_data["count"],
    }
