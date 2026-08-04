from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, List, Optional
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    period_type: str = Query("all", regex="^(all|monthly|yearly)$"),
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2020, le=2030),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:

    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"
    
    # Get property timezone from database
    timezone_str = "UTC"
    try:
        from app.core.database_pool import DatabasePool
        from sqlalchemy import text

        db_pool = DatabasePool()
        await db_pool.initialize()

        async with db_pool.get_session() as session:
            result = await session.execute(
                text("SELECT timezone FROM properties WHERE id = :property_id AND tenant_id = :tenant_id"),
                {"property_id": property_id, "tenant_id": tenant_id},
            )
            row = result.fetchone()
            if row and row.timezone:
                timezone_str = row.timezone
    except Exception as e:
        print(f"Error fetching property timezone: {e}")

    revenue_data = await get_revenue_summary(
        property_id=property_id,
        tenant_id=tenant_id,
        period_type=period_type,
        month=month,
        year=year,
        timezone_str=timezone_str,
    )

    # Return total as string to preserve Decimal precision
    return {
        "property_id": revenue_data["property_id"],
        "total_revenue": revenue_data["total"],
        "currency": revenue_data["currency"],
        "reservations_count": revenue_data["count"],
        "period_type": period_type,
        "timezone": timezone_str,
    }


@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:

    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant not resolved")

    from app.core.database_pool import DatabasePool
    from sqlalchemy import text

    db_pool = DatabasePool()
    await db_pool.initialize()

    async with db_pool.get_session() as session:
        result = await session.execute(
            text(
                "SELECT id, name, timezone FROM properties WHERE tenant_id = :tenant_id ORDER BY name"
            ),
            {"tenant_id": tenant_id},
        )
        rows = result.fetchall()

    return [{"id": row.id, "name": row.name, "timezone": row.timezone} for row in rows]
