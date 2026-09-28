import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from typing import Dict, Any, Optional
from decimal import Decimal, ROUND_HALF_UP
from app.services.cache import get_revenue_summary
from app.services.reservations import get_tenant_properties, get_reservations, property_belongs_to_tenant
from app.core.auth import authenticate_request as get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


def get_tenant_id(current_user) -> str:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant for this user")
    return tenant_id


def db_unavailable(e: Exception):
    logger.error(f"Dashboard query failed: {e}")
    return HTTPException(status_code=503, detail="Dashboard data is unavailable, try again shortly")


async def check_property(property_id: str, tenant_id: str):
    try:
        found = await property_belongs_to_tenant(property_id, tenant_id)
    except (SQLAlchemyError, OSError) as e:
        raise db_unavailable(e)
    if not found:
        raise HTTPException(status_code=404, detail="Property not found")


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = None,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:

    tenant_id = get_tenant_id(current_user)
    await check_property(property_id, tenant_id)

    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id, month, year)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except (SQLAlchemyError, OSError) as e:
        raise db_unavailable(e)

    total_revenue = Decimal(revenue_data['total']).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": float(total_revenue),
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }


@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    tenant_id = get_tenant_id(current_user)
    try:
        return {"properties": await get_tenant_properties(tenant_id)}
    except (SQLAlchemyError, OSError) as e:
        raise db_unavailable(e)


@router.get("/dashboard/reservations")
async def get_dashboard_reservations(
    property_id: str,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = None,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    tenant_id = get_tenant_id(current_user)
    await check_property(property_id, tenant_id)
    try:
        return {"reservations": await get_reservations(property_id, tenant_id, month, year)}
    except (SQLAlchemyError, OSError) as e:
        raise db_unavailable(e)
