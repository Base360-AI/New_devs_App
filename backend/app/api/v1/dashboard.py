from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    
    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"
    
    revenue_data = await get_revenue_summary(property_id, tenant_id)
    
    # Bug 3 (possibly a bug):
    # I'm not entirely sure if this conversion won't lead to bugs
    # UPD: I have a feeling that there are quite many conversion and it can be a problem
    # NUMERIC(10,3) -> Decimal -> str -> Redis -> str -> float() -> JS Math.round
    # Needs deeper investigation.
    total_revenue_float = float(revenue_data['total'])
    
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": total_revenue_float,
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }


@router.get("/dashboard/properties")
async def get_tenant_properties(
    current_user: dict = Depends(get_current_user)
) -> List[Dict[str, str]]:
    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"

    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        from sqlalchemy import text
        from app.config import settings

        db_url = settings.database_url.replace("postgresql://", "postgresql+asyncpg://")
        engine = create_async_engine(db_url)

        async with engine.connect() as conn:
            query = text("""
                SELECT id, name FROM properties
                WHERE tenant_id = :tenant_id
                ORDER BY name
            """)
            result = await conn.execute(query, {"tenant_id": tenant_id})
            rows = result.fetchall()
            return [{"id": row.id, "name": row.name} for row in rows]
    except Exception as e:
        print(f"Error: {e}")

    return []
