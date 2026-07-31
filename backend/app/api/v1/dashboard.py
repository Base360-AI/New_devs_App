import logging
from decimal import Decimal, ROUND_HALF_UP
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

CENTS = Decimal('0.01')

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:

    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"

    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id)
    except Exception as e:
        # Surface the outage instead of serving substitute figures: a revenue
        # dashboard must never display numbers it cannot attribute to real data.
        logger.error(f"Revenue lookup failed for {property_id} (tenant: {tenant_id}): {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Revenue data is temporarily unavailable",
        )

    # Round with Decimal before converting to float so currency (stored with
    # sub-cent precision) doesn't drift due to binary floating-point error.
    total_revenue_decimal = Decimal(str(revenue_data['total'])).quantize(CENTS, rounding=ROUND_HALF_UP)

    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": float(total_revenue_decimal),
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
