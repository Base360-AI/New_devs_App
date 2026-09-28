import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import SQLAlchemyError

from app.core.auth import authenticate_request as get_current_user
from app.models.auth import AuthenticatedUser
from app.services.cache import get_revenue_summary
from app.services.reservations import PropertyNotFoundError, list_tenant_properties

logger = logging.getLogger(__name__)
router = APIRouter()


def _tenant_id(current_user: AuthenticatedUser) -> str:
    """Require tenant context instead of silently using a shared fallback."""
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A tenant context is required for dashboard data",
        )
    return current_user.tenant_id


@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, list[dict[str, str]]]:
    """List only the current tenant's selectable dashboard properties."""
    try:
        properties = await list_tenant_properties(_tenant_id(current_user))
        return {"items": properties}
    except SQLAlchemyError as error:
        logger.exception("Unable to load dashboard properties: %s", error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Property data is temporarily unavailable",
        ) from error


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    year: int = Query(default=2024, ge=2000, le=2100),
    month: int = Query(default=3, ge=1, le=12),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Return exact monthly revenue for one tenant-owned property."""
    try:
        revenue_data = await get_revenue_summary(
            property_id,
            _tenant_id(current_user),
            year=year,
            month=month,
        )
    except PropertyNotFoundError as error:
        # Do not reveal whether the property exists for another tenant.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found") from error
    except SQLAlchemyError as error:
        logger.exception("Unable to load dashboard revenue: %s", error)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Revenue data is temporarily unavailable",
        ) from error

    return {
        "property_id": revenue_data["property_id"],
        "property_name": revenue_data["property_name"],
        "year": revenue_data["year"],
        "month": revenue_data["month"],
        "timezone": revenue_data["timezone"],
        # A decimal string avoids introducing a binary floating-point value at
        # the API boundary.
        "total_revenue": revenue_data["total"],
        "currency": revenue_data["currency"],
        "reservations_count": revenue_data["count"],
    }
