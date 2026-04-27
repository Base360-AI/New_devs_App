from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from datetime import datetime
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: int = None,
    year: int = None,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    if month is not None and (month < 1 or month > 12):
        raise HTTPException(status_code=400, detail="Month must be between 1 and 12")

    if year is not None and (year < 2000 or year > 2100):
        raise HTTPException(status_code=400, detail="Year must be between 2000 and 2100")

    # Default to current month/year if not provided
    if month is None:
        month = datetime.now().month
    if year is None:
        year = datetime.now().year

    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    revenue_data = await get_revenue_summary(property_id, tenant_id, month, year)

    # Return as string to preserve precision
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": revenue_data['total'],  # Keep as string
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count'],
        "month": month,
        "year": year
    }
