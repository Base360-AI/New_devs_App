from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import Dict, Any, List
from app.services.cache import get_revenue_summary
from app.services.reservations import list_tenant_properties
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()


def _tenant_id(current_user: Any) -> str:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authenticated user has no tenant context",
        )
    return tenant_id


@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, str]]:
    return await list_tenant_properties(_tenant_id(current_user))


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: int | None = Query(default=None, ge=1, le=12),
    year: int | None = Query(default=None, ge=1),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    if (month is None) != (year is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="month and year must be provided together",
        )

    revenue_data = await get_revenue_summary(
        property_id, _tenant_id(current_user), month, year
    )
    
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": revenue_data['total'],
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
