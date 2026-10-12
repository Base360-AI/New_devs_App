import logging
from fastapi import APIRouter, Depends, HTTPException
from decimal import Decimal
from typing import Dict, Any
from app.services.cache import get_revenue_summary
from app.services.reservations import to_cents, PropertyNotFoundError, list_tenant_properties
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    
    # Never fall back to a shared/default tenant - that would mix clients' data.
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant associated with this user")
    
    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id)
    except HTTPException:
        raise
    except PropertyNotFoundError:
        raise HTTPException(status_code=404, detail="Property not found")
    except Exception:
        logger.exception("Failed to load revenue summary for property %s (tenant %s)", property_id, tenant_id)
        raise HTTPException(status_code=503, detail="Revenue data temporarily unavailable")
    
    # Total is an exact 2-decimal Decimal string; convert once for JSON (a 2dp value is float-safe).
    total_revenue = float(to_cents(Decimal(str(revenue_data['total']))))
    
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": total_revenue,
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }


@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    """Properties belonging to the logged-in tenant (drives the dashboard dropdown)."""
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant associated with this user")

    try:
        properties = await list_tenant_properties(tenant_id)
    except Exception:
        logger.exception("Failed to list properties for tenant %s", tenant_id)
        raise HTTPException(status_code=503, detail="Properties temporarily unavailable")

    return {"properties": properties}
