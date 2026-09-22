from decimal import Decimal, ROUND_HALF_UP
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import SQLAlchemyError
from typing import Dict, Any
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user
from app.models.auth import AuthenticatedUser
from app.services.reservations import list_revenue_properties

router = APIRouter()
logger = logging.getLogger(__name__)


def require_tenant(current_user: AuthenticatedUser) -> str:
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant required")
    return current_user.tenant_id


@router.get("/dashboard/properties")
async def get_dashboard_properties(current_user: AuthenticatedUser = Depends(get_current_user)):
    tenant_id = require_tenant(current_user)
    try:
        return await list_revenue_properties(tenant_id)
    except (SQLAlchemyError, OSError):
        logger.exception("Revenue property lookup failed")
        raise HTTPException(status_code=503, detail="Revenue data unavailable")

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=1, le=9998),
    current_user: AuthenticatedUser = Depends(get_current_user)
) -> Dict[str, Any]:
    
    tenant_id = require_tenant(current_user)
    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id, month, year)
    except (SQLAlchemyError, OSError):
        logger.exception("Revenue calculation failed")
        raise HTTPException(status_code=503, detail="Revenue data unavailable")

    # Round once, after the NUMERIC sum. JSON strings preserve decimal precision.
    total_revenue = Decimal(revenue_data['total']).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": format(total_revenue, '.2f'),
        "month": month,
        "year": year,
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
