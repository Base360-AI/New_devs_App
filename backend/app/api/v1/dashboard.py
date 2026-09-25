import logging
from decimal import Decimal, ROUND_HALF_UP
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, List, Optional
from app.services.cache import get_revenue_summary
from app.services.reservations import list_tenant_properties
from app.core.auth import authenticate_request as get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

# [LEAK] New endpoint: the property dropdown was hardcoded, showing every tenant's properties to everyone
@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: dict = Depends(get_current_user)
) -> List[Dict[str, Any]]:

    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant associated with this user")

    try:
        return await list_tenant_properties(tenant_id)
    except Exception as e:
        logger.error(f"Property list failed (tenant: {tenant_id}): {e}")
        raise HTTPException(status_code=503, detail="Property list is temporarily unavailable")

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:

    # [LEAK] Was falling back to a shared "default_tenant"; now a user without a tenant is refused
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant associated with this user")

    if (month is None) != (year is None):
        raise HTTPException(status_code=422, detail="month and year must be provided together")

    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id, month, year)
    except Exception as e:
        logger.error(f"Revenue summary failed for {property_id} (tenant: {tenant_id}): {e}")
        raise HTTPException(status_code=503, detail="Revenue data is temporarily unavailable")

    if revenue_data is None:
        raise HTTPException(status_code=404, detail="Property not found")

    # [CENTS] Was float(total): round the exact Decimal sum once (half-up) and send it as a string, never as a float
    total_revenue = Decimal(revenue_data['total']).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    return {
        "property_id": revenue_data['property_id'],
        "month": revenue_data.get('month'),
        "year": revenue_data.get('year'),
        "total_revenue": str(total_revenue),
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
