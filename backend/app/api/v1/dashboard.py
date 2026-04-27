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
    
    # 1. Clean up the tenant fallback (Safety first)
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant ID missing from session")
    
    # 2. Fetch the data (Now returns a string from your new service logic)
    revenue_data = await get_revenue_summary(property_id, tenant_id)
    
    # 3. Return the data AS IS (Keep the string for precision)
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": revenue_data['total'], # NO FLOAT CASTING!
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }