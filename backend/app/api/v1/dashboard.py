import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import SQLAlchemyError

from app.core.auth import authenticate_request
from app.models.auth import AuthenticatedUser
from app.services.cache import get_revenue_summary

router = APIRouter()
logger = logging.getLogger(__name__)


def dashboard_tenant(user: AuthenticatedUser = Depends(authenticate_request)) -> str:
    if not user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant access required")
    return user.tenant_id


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    response: Response,
    property_id: str = Query(min_length=1, max_length=200),
    year: int = Query(ge=2, le=9998),
    month: int | None = Query(default=None, ge=1, le=12),
    tenant_id: str = Depends(dashboard_tenant),
) -> dict:
    response.headers["Cache-Control"] = "private, no-store"
    try:
        revenue = await get_revenue_summary(property_id, tenant_id, year, month)
    except (SQLAlchemyError, OSError, ValueError, KeyError):
        logger.exception("Revenue calculation failed")
        raise HTTPException(status_code=503, detail="Revenue data temporarily unavailable")
    return {
        "property_id": revenue["property_id"],
        "year": revenue["year"], "month": revenue["month"], "timezone": revenue["timezone"],
        "total_revenue": revenue["total"], "currency": revenue["currency"],
        "totals_by_currency": revenue["totals_by_currency"],
        "reservations_count": revenue["count"],
    }
