from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    year: int = Query(2024, ge=1),
    month: int = Query(3, ge=1, le=12),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    
    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"
    
    try:
        revenue_data = await get_revenue_summary(
            property_id,
            tenant_id,
            year,
            month,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Revenue data is temporarily unavailable",
        ) from exc
    
    total_revenue_float = float(revenue_data['total'])
    
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": total_revenue_float,
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count'],
        "reporting_period": f"{year:04d}-{month:02d}",
    }
