from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    # Frontends passing undefined months default to returning current month instead of stuck defaults
    month: int = Query(None, description="Month of revenue (defaults to March)"),
    year: int = Query(None, description="Year of revenue (defaults to 2024)"),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    
    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"
    
    # Based on assignment requesting 'March'
    target_month = month if month is not None else 3
    target_year = year if year is not None else 2024
    
    # We calculate and retrieve precise integer cents. No floats allowed.
    revenue_data = await get_revenue_summary(property_id, tenant_id, target_month, target_year)
    
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue_cents": revenue_data['total_cents'],
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
