import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user
from app.models.auth import AuthenticatedUser

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/dashboard/properties")
async def get_dashboard_properties(current_user: AuthenticatedUser = Depends(get_current_user)):
    from app.core.database_pool import db_pool
    from sqlalchemy import text
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant membership required")
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        result = await session.execute(text(
            "SELECT id, name FROM properties WHERE tenant_id = :tenant_id ORDER BY id"
        ), {"tenant_id": current_user.tenant_id})
        return [dict(row._mapping) for row in result.fetchall()]


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    response: Response,
    property_id: str,
    month: int = Query(3, ge=1, le=12),
    year: int = Query(2024, ge=1, le=9998),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> Dict[str, Any]:
    response.headers["Cache-Control"] = "private, no-store"
    tenant_id = current_user.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant membership required")
    try:
        data = await get_revenue_summary(property_id, tenant_id, month, year)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Revenue calculation failed")
        raise HTTPException(status_code=503, detail="Revenue data temporarily unavailable")
    return {
        "property_id": data["property_id"], "month": month, "year": year,
        "total_revenue": data["total"], "currency": data["currency"],
        "reservations_count": data["count"], "totals": data["totals"],
    }
