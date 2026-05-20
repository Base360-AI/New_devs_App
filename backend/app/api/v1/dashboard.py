from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:

    # SECURITY: Never silently fall back to a shared "default_tenant" - that
    # would merge multiple clients into the same tenant bucket and is exactly
    # the kind of cross-tenant leak we are trying to prevent.
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(
            status_code=403,
            detail="Authenticated user has no tenant context; refusing to serve revenue data",
        )

    revenue_data = await get_revenue_summary(property_id, tenant_id)

    # PRECISION: Keep the total as the exact decimal string produced by the
    # database/Decimal pipeline. Converting to float here was rounding to the
    # nearest IEEE-754 double and silently dropping sub-cent precision, which
    # is what the finance team has been seeing as "off by a few cents".
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": revenue_data['total'],
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count'],
    }
