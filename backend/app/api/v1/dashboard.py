from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from app.core.auth import authenticate_request
from app.core.database_pool import DatabasePool
from app.services.reservations import calculate_monthly_revenue

router = APIRouter()


@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user=Depends(authenticate_request),
):
    tenant_id = current_user.tenant_id

    if not tenant_id:
        raise ValueError("Authenticated user has no tenant")

    db_pool = DatabasePool()
    await db_pool.initialize()

    if not db_pool.session_factory:
        raise RuntimeError("Database pool is not available")

    try:
        async with db_pool.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT id, name
                    FROM properties
                    WHERE tenant_id = :tenant_id
                    ORDER BY name
                """),
                {"tenant_id": tenant_id},
            )

            items = [
                {"id": row.id, "name": row.name}
                for row in result.fetchall()
            ]

            return {"items": items, "total": len(items)}
    finally:
        await db_pool.close()


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: int = Query(..., ge=1, le=12),
    year: int = Query(..., ge=2000, le=2100),
    current_user=Depends(authenticate_request),
):
    tenant_id = current_user.tenant_id

    if not tenant_id:
        raise ValueError("Authenticated user has no tenant")

    db_pool = DatabasePool()
    await db_pool.initialize()

    if not db_pool.session_factory:
        raise RuntimeError("Database pool is not available")

    try:
        async with db_pool.get_session() as session:
            total = await calculate_monthly_revenue(
                property_id=property_id,
                tenant_id=tenant_id,
                month=month,
                year=year,
                db_session=session,
            )

        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total_revenue": str(total),
            "currency": "USD",
        }

    finally:
        await db_pool.close()