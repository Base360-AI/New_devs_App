from decimal import ROUND_HALF_UP, Decimal
from app.models.auth import AuthenticatedUser
from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: int = 3,
    year: int = 2024,
    current_user: AuthenticatedUser = Depends(get_current_user)
) -> Dict[str, Any]:
    
    tenant_id = current_user.tenant_id

    if not tenant_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="month must be 1-12")
    
    revenue_data = await get_revenue_summary(property_id, tenant_id, month=month, year=year)
    
    total_revenue = Decimal(str(revenue_data['total'])).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": str(total_revenue),
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
