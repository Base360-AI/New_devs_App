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

    # FIX: Do NOT convert to float - floats lose precision for financial data
    # Previously: total_revenue_float = float(revenue_data['total']) caused rounding errors
    # Example: 333.333 + 333.333 + 333.334 = 1000.000 but float arithmetic loses cents
    # Keep as string to preserve exact decimal precision from database

    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": revenue_data['total'],  # Keep as string for precision
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
