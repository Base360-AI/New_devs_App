from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, List, Optional
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()


def _require_tenant(current_user) -> str:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="User is not assigned to a tenant")
    return tenant_id


@router.get("/dashboard/properties")
async def get_dashboard_properties(current_user: dict = Depends(get_current_user)) -> List[Dict[str, str]]:
    tenant_id = _require_tenant(current_user)

    from app.core.database_pool import db_pool
    from sqlalchemy import text

    try:
        await db_pool.initialize()
        async with db_pool.get_session() as session:
            result = await session.execute(
                text("SELECT id, name FROM properties WHERE tenant_id = :tenant_id ORDER BY id"),
                {"tenant_id": tenant_id},
            )
            return [{"id": row.id, "name": row.name} for row in result]
    except Exception:
        raise HTTPException(status_code=503, detail="Properties are temporarily unavailable")


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    
    tenant_id = _require_tenant(current_user)

    if (month is None) != (year is None):
        raise HTTPException(status_code=400, detail="month and year must be provided together")

    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id, month, year)
    except Exception:
        raise HTTPException(status_code=503, detail="Revenue data is temporarily unavailable")
    
    return {
        "property_id": revenue_data['property_id'],
        # Sent as a decimal string; floats lose cents.
        "total_revenue": revenue_data['total'],
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
