from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, Optional
from decimal import Decimal, ROUND_HALF_UP
import logging

from app.services.cache import get_revenue_summary
from app.services.reservations import PropertyNotFound, list_tenant_properties
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

CENTS = Decimal("0.01")


def _require_tenant(current_user) -> str:
    """Resolve the caller's tenant from their authenticated identity.

    There is deliberately no default tenant: a placeholder like
    "default_tenant" would put every client into one shared bucket.
    """
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        logger.error(f"Authenticated user {getattr(current_user, 'email', '?')} has no tenant_id")
        raise HTTPException(status_code=403, detail="No tenant associated with this account")
    return tenant_id


@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Properties visible to the caller — their own tenant's, and only those."""
    tenant_id = _require_tenant(current_user)
    return {"properties": await list_tenant_properties(tenant_id)}


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = Query(None, ge=1, le=12, description="Calendar month in the property's local timezone"),
    year: Optional[int] = Query(None, ge=1970, le=2100),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:

    tenant_id = _require_tenant(current_user)

    if (month is None) != (year is None):
        raise HTTPException(status_code=400, detail="month and year must be supplied together")

    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id, month, year)
    except PropertyNotFound:
        # Same response whether the property belongs to someone else or does not
        # exist, so the endpoint cannot be used to probe other tenants.
        raise HTTPException(status_code=404, detail="Property not found")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    # Money stays in Decimal and is rounded exactly once, here at the edge.
    # float() on the way out is what turned exact sums into "a few cents off".
    total_exact = Decimal(revenue_data["total"])
    total_rounded = total_exact.quantize(CENTS, rounding=ROUND_HALF_UP)

    return {
        "property_id": revenue_data["property_id"],
        "total_revenue": str(total_rounded),
        "total_revenue_exact": str(total_exact),
        "currency": revenue_data["currency"],
        "reservations_count": revenue_data["count"],
        "period": revenue_data.get("period", "all-time"),
        "timezone": revenue_data.get("timezone", "UTC"),
    }
