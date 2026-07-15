from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, Optional
from app.services.cache import get_revenue_summary, get_monthly_revenue_summary
from app.core.auth import authenticate_request as get_current_user
from decimal import Decimal, ROUND_HALF_UP


router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    
    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"
    
    if month is not None and year is not None:
        revenue_data = await get_monthly_revenue_summary(property_id, tenant_id, month, year)
    else:
        revenue_data = await get_revenue_summary(property_id, tenant_id)
        
    total_revenue_float = float(Decimal(revenue_data['total']).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
    
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": total_revenue_float,
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }

# NOTE: The frontend already calls this endpoint (secureApi.ts's getProperties()),
# but it never existed on the backend — Dashboard.tsx worked around the missing
# endpoint by hardcoding a list of ALL properties across every tenant, which
# leaked other companies' property names to any logged-in user. This completes
# the missing endpoint, scoped correctly by tenant_id, so the frontend can use
# real data instead of the hardcoded workaround.

@router.get("/properties")
async def get_properties(
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"

    from app.core.database_pool import DatabasePool
    from sqlalchemy import text

    db_pool = DatabasePool()
    await db_pool.initialize()

    if not db_pool.session_factory:
        return {"items": [], "total": 0}

    async with db_pool.get_session() as session:
        query = text("""
            SELECT id, name, timezone FROM properties
            WHERE tenant_id = :tenant_id
            ORDER BY id
        """)
        result = await session.execute(query, {"tenant_id": tenant_id})
        rows = result.fetchall()

        items = [{"id": row.id, "name": row.name, "timezone": row.timezone} for row in rows]
        return {"items": items, "total": len(items)}