import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import authenticate_request as get_current_user
from app.services.cache import get_revenue_summary
from app.services.reservations import (
    DEFAULT_REPORT_MONTH,
    DEFAULT_REPORT_YEAR,
    list_tenant_properties,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _tenant_id(current_user) -> str:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context missing")
    return tenant_id


@router.get("/properties")
async def get_properties(current_user: dict = Depends(get_current_user)):
    tenant_id = _tenant_id(current_user)
    try:
        properties = await list_tenant_properties(tenant_id)
    except Exception as exc:
        logger.error("property list failed tenant_id=%s error=%s", tenant_id, exc)
        raise HTTPException(status_code=503, detail="Property data is temporarily unavailable")
    return {"data": properties, "total": len(properties)}


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: int = Query(DEFAULT_REPORT_MONTH, ge=1, le=12),
    year: int = Query(DEFAULT_REPORT_YEAR, ge=2000, le=2100),
    current_user: dict = Depends(get_current_user),
):
    tenant_id = _tenant_id(current_user)
    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id, year, month)
    except Exception as exc:
        logger.error(
            "revenue summary failed property_id=%s tenant_id=%s error=%s",
            property_id,
            tenant_id,
            exc,
        )
        raise HTTPException(status_code=503, detail="Revenue data is temporarily unavailable")

    if revenue_data is None:
        raise HTTPException(status_code=404, detail="Property not found")

    return {
        "property_id": revenue_data["property_id"],
        "property_name": revenue_data["property_name"],
        "timezone": revenue_data["timezone"],
        "year": revenue_data["year"],
        "month": revenue_data["month"],
        "total_revenue": revenue_data["total"],
        "currency": revenue_data["currency"],
        "reservations_count": revenue_data["count"],
    }