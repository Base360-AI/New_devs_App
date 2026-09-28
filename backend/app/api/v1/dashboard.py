from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Any, Dict, List
from sqlalchemy import text
from app.services.cache import get_revenue_summary
from app.services.reservations import PropertyNotFoundError, RevenueServiceError
from app.core.auth import authenticate_request as get_current_user
from app.core.database_pool import db_pool

router = APIRouter()


@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: dict = Depends(get_current_user)
) -> List[Dict[str, str]]:
    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"

    try:
        async with db_pool.get_session() as session:
            result = await session.execute(text("""
                SELECT id, name
                FROM properties
                WHERE tenant_id = :tenant_id
                ORDER BY name
            """), {"tenant_id": tenant_id})
            return [
                {"id": row.id, "name": row.name}
                for row in result.fetchall()
            ]
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail="Properties are temporarily unavailable",
        ) from error


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    year: int = Query(ge=1, le=9998),
    month: int = Query(ge=1, le=12),
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
    except PropertyNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail="Property not found",
        ) from error
    except RevenueServiceError as error:
        raise HTTPException(
            status_code=503,
            detail="Revenue data is temporarily unavailable",
        ) from error
    
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": revenue_data['total'],
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
