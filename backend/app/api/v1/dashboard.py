from decimal import Decimal, ROUND_HALF_UP
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user
from app.api.v1.properties import _TENANT_PROPERTIES

router = APIRouter()


def _tenant_owns_property(tenant_id: str, property_id: str) -> bool:
    """Return True if the property belongs to this tenant (DB fallback uses seed data)."""
    owned = {p['id'] for p in _TENANT_PROPERTIES.get(tenant_id, [])}
    return property_id in owned


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:

    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"

    # Prevent tenants from querying properties that belong to other tenants.
    if not _tenant_owns_property(tenant_id, property_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Property does not belong to your account."
        )

    revenue_data = await get_revenue_summary(property_id, tenant_id)

    # Keep as Decimal to avoid float binary-representation errors (e.g. 333.333*3 in float
    # produces 999.999... instead of 1000.000). Round to 2 decimal places for display.
    total_revenue = Decimal(revenue_data['total']).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": str(total_revenue),
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
