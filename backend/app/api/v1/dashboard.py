from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi import Query
from typing import Dict, Any
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = Query(default=None, ge=1, le=12),
    year: Optional[int] = Query(default=None, ge=1),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    if (month is None) != (year is None):
        raise HTTPException(status_code=422, detail="Both month and year are required")

    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant is associated with this user")

    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id, month, year)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": float(Decimal(revenue_data['total'])),
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
