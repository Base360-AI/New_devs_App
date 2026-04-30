from decimal import Decimal, ROUND_HALF_UP
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, List
from sqlalchemy import text
from app.services.cache import get_revenue_summary
from app.services.reservations import calculate_monthly_revenue
from app.core.auth import authenticate_request as get_current_user
from app.core.database_pool import DatabasePool

router = APIRouter()


def _round_to_cents(value: str) -> float:
    return float(Decimal(value).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def _require_tenant(current_user) -> str:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=400, detail="No tenant context for user")
    return tenant_id


@router.get("/dashboard/properties")
async def get_properties(current_user = Depends(get_current_user)) -> Dict[str, List[Dict[str, Any]]]:
    tenant_id = _require_tenant(current_user)

    db_pool = DatabasePool()
    await db_pool.initialize()
    if not db_pool.session_factory:
        raise HTTPException(status_code=503, detail="Database unavailable")

    async with db_pool.get_session() as session:
        result = await session.execute(
            text("SELECT id, name, timezone FROM properties WHERE tenant_id = :tenant_id ORDER BY id"),
            {"tenant_id": tenant_id},
        )
        properties = [
            {"id": row.id, "name": row.name, "timezone": row.timezone}
            for row in result.fetchall()
        ]
    return {"properties": properties}


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant_id = _require_tenant(current_user)
    revenue_data = await get_revenue_summary(property_id, tenant_id)

    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": _round_to_cents(revenue_data['total']),
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }


@router.get("/dashboard/monthly")
async def get_dashboard_monthly(
    property_id: str,
    month: int = Query(3, ge=1, le=12),
    year: int = Query(2024, ge=2000, le=2100),
    current_user = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant_id = _require_tenant(current_user)
    monthly = await calculate_monthly_revenue(property_id, tenant_id, month, year)

    return {
        "property_id": monthly["property_id"],
        "month": monthly["month"],
        "year": monthly["year"],
        "total_revenue": _round_to_cents(monthly["total"]),
        "currency": monthly["currency"],
        "reservations_count": monthly["count"],
    }
