from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, List, Optional
from decimal import Decimal, ROUND_HALF_UP
import logging
from app.services.cache import get_revenue_summary
from app.services.reservations import (
    get_tenant_properties,
    get_tenant_property,
    PropertyNotFoundError,
    MixedCurrencyError,
)
from app.core.auth import authenticate_request as get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


def get_user_tenant_id(current_user) -> str:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="User is not assigned to a tenant")
    return tenant_id


@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: dict = Depends(get_current_user)
) -> List[Dict[str, Any]]:

    tenant_id = get_user_tenant_id(current_user)

    try:
        return await get_tenant_properties(tenant_id)
    except Exception as e:
        logger.error(f"Failed to load properties for tenant {tenant_id}: {e}")
        raise HTTPException(status_code=503, detail="Property data is temporarily unavailable")


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    year: Optional[int] = Query(None, ge=2000, le=2100),
    month: Optional[int] = Query(None, ge=1, le=12),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:

    tenant_id = get_user_tenant_id(current_user)

    if month is not None and year is None:
        raise HTTPException(status_code=400, detail="month requires year")

    try:
        # Check ownership before touching the cache
        if not await get_tenant_property(property_id, tenant_id):
            raise PropertyNotFoundError(property_id)

        revenue_data = await get_revenue_summary(property_id, tenant_id, year=year, month=month)
    except PropertyNotFoundError:
        raise HTTPException(status_code=404, detail="Property not found")
    except MixedCurrencyError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to load revenue for {property_id} (tenant: {tenant_id}): {e}")
        raise HTTPException(status_code=503, detail="Revenue data is temporarily unavailable")

    # Round to cents only for display, keeping the exact amount out of floats
    total_revenue = Decimal(revenue_data['total']).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "property_id": revenue_data['property_id'],
        "tenant_id": tenant_id,
        "timezone": revenue_data['timezone'],
        "year": revenue_data['year'],
        "month": revenue_data['month'],
        "total_revenue": str(total_revenue),
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
