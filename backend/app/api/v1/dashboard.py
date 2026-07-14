from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, Optional
from decimal import Decimal
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user
from app.models.auth import AuthenticatedUser
from app.core.database_pool import DatabasePool
from sqlalchemy import text

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
    current_user: AuthenticatedUser = Depends(get_current_user)
) -> Dict[str, Any]:

    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context missing")
    # Ensure the requested property belongs to the authenticated tenant
    try:
        db_pool = DatabasePool()
        await db_pool.initialize()
        async with (await db_pool.get_session()) as session:
            ownership = await session.execute(
                text("SELECT 1 FROM properties WHERE id = :property_id AND tenant_id = :tenant_id LIMIT 1"),
                {"property_id": property_id, "tenant_id": tenant_id},
            )
            if not ownership.fetchone():
                raise HTTPException(status_code=403, detail="Property not found for tenant")
    except HTTPException:
        raise
    except Exception:
        # If DB lookup fails for some reason, deny access rather than risk data leakage
        raise HTTPException(status_code=403, detail="Property access denied")
    
    revenue_data = await get_revenue_summary(property_id, tenant_id, month=month, year=year)
    
    # Use Decimal to preserve precision, then round to 2 decimal places
    total = Decimal(revenue_data['total']).quantize(Decimal('0.01'))
    
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": float(total),
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count'],
        "month": revenue_data.get('month'),
        "year": revenue_data.get('year'),
        "timezone": revenue_data.get('timezone')
    }
