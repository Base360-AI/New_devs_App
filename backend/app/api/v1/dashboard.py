from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, Optional
from decimal import Decimal
from app.services.cache import get_revenue_summary
from app.services.reservations import calculate_monthly_revenue
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = Query(None, description="Month for monthly revenue (1-12)"),
    year: Optional[int] = Query(None, description="Year for monthly revenue"),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    
    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"
    
    # If month and year are provided, calculate monthly revenue (timezone-aware)
    if month is not None and year is not None:
        monthly_revenue = await calculate_monthly_revenue(property_id, month, year, tenant_id)
        return {
            "property_id": property_id,
            "monthly_revenue": str(monthly_revenue),
            "month": month,
            "year": year,
            "currency": "USD"
        }
    
    # Otherwise, return total revenue (current implementation)
    revenue_data = await get_revenue_summary(property_id, tenant_id)
    
    # Preserve decimal precision by using string instead of float conversion
    total_revenue_str = revenue_data['total']
    
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": total_revenue_str,
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
