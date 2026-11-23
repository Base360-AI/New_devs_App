import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import authenticate_request as get_current_user
from app.models.auth import AuthenticatedUser
from app.services.cache import get_revenue_summary
from app.services.reservations import (
    MixedCurrencyError,
    PropertyNotFoundError,
    list_properties,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_tenant(current_user: AuthenticatedUser) -> str:
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="No active tenant membership")
    return current_user.tenant_id


@router.get("/properties")
async def get_dashboard_properties(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant_id = _require_tenant(current_user)
    try:
        properties = await list_properties(tenant_id, page, page_size)
    except Exception:
        logger.exception("Unable to load properties")
        raise HTTPException(status_code=503, detail="Property data unavailable")

    return {"items": properties, "total": len(properties)}


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    year: int = Query(ge=1900, le=9998),
    month: Optional[int] = Query(default=None, ge=1, le=12),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant_id = _require_tenant(current_user)
    try:
        revenue_data = await get_revenue_summary(
            property_id, tenant_id, year, month
        )
    except PropertyNotFoundError:
        raise HTTPException(status_code=404, detail="Property not found")
    except MixedCurrencyError:
        raise HTTPException(
            status_code=409,
            detail="Mixed currencies require separate reporting",
        )
    except Exception:
        logger.exception("Unable to calculate revenue")
        raise HTTPException(status_code=503, detail="Revenue data unavailable")

    return {
        "property_id": revenue_data["property_id"],
        "property_name": revenue_data["property_name"],
        "total_revenue": revenue_data["total"],
        "currency": revenue_data["currency"],
        "reservations_count": revenue_data["count"],
        "year": revenue_data["year"],
        "month": revenue_data["month"],
        "timezone": revenue_data["timezone"],
    }
