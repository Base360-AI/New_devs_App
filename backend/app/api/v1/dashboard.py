from typing import Annotated, Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query

from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user
from app.models.auth import AuthenticatedUser
from app.services.reservations import (
    MixedCurrencyError,
    PropertyNotFoundError,
    get_tenant_properties,
)

router = APIRouter()


def _require_tenant(current_user: AuthenticatedUser) -> str:
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(
            status_code=403,
            detail="Authenticated user is not assigned to a tenant",
        )
    return tenant_id


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Annotated[int, Query(ge=1, le=12)],
    year: Annotated[int, Query(ge=2000, le=2100)],
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> Dict[str, Any]:
    tenant_id = _require_tenant(current_user)

    try:
        revenue_data = await get_revenue_summary(
            property_id, tenant_id, month, year
        )
    except PropertyNotFoundError:
        raise HTTPException(
            status_code=404, detail="Property not found"
        ) from None
    except MixedCurrencyError:
        raise HTTPException(
            status_code=422,
            detail="Revenue cannot combine multiple currencies",
        ) from None

    return {
        "property_id": revenue_data["property_id"],
        "month": revenue_data["month"],
        "year": revenue_data["year"],
        "total_revenue": revenue_data["total"],
        "currency": revenue_data["currency"],
        "reservations_count": revenue_data["count"],
    }


@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> List[Dict[str, str]]:
    tenant_id = _require_tenant(current_user)
    return await get_tenant_properties(tenant_id)
