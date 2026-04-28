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
    
    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"
    
    revenue_data = await get_revenue_summary(property_id, tenant_id)
    
    # Return total_revenue as a string representation of the Decimal value to
    # preserve exact precision. Converting to float (IEEE 754) introduces
    # sub-cent rounding errors for values with 3 decimal places (NUMERIC(10,3)).
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": str(revenue_data['total']),
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
