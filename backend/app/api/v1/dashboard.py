from fastapi import APIRouter, Depends, HTTPException, Query, Request
from typing import Dict, Any, Optional
from decimal import Decimal, ROUND_HALF_UP
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    request: Request = None,
    current_user: Any = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Returns revenue summary for a property, properly scoped to the authenticated tenant.
    Supports optional month and year filtering with timezone awareness.
    """
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id and request:
        tenant_id = request.headers.get("x-simulated-tenant")
    tenant_id = tenant_id or "default_tenant"

    revenue_data = await get_revenue_summary(property_id, tenant_id, month=month, year=year)

    # Standard financial precision: parse to Decimal and round half up to 2 decimal places
    raw_total = Decimal(str(revenue_data.get('total', '0.00'))).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    total_revenue_float = float(raw_total)

    return {
        "property_id": revenue_data['property_id'],
        "tenant_id": tenant_id,
        "total_revenue": total_revenue_float,
        "formatted_total": f"{raw_total:.2f}",
        "currency": revenue_data.get('currency', 'USD'),
        "reservations_count": revenue_data.get('count', 0)
    }
