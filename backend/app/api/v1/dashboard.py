import logging
import re
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from app.core.auth import authenticate_request as get_current_user
from app.core.database_pool import db_pool
from app.services.cache import get_revenue_summary

router = APIRouter()
logger = logging.getLogger(__name__)


def tenant_for(user) -> str:
    tenant_id = getattr(user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant is assigned to this account")
    return tenant_id


@router.get("/dashboard/properties")
async def get_dashboard_properties(current_user=Depends(get_current_user)):
    tenant_id = tenant_for(current_user)
    try:
        if not db_pool.session_factory:
            await db_pool.initialize()
        async with db_pool.get_session() as session:
            rows = (await session.execute(text("""
                SELECT id, name FROM properties
                WHERE tenant_id = :tenant_id ORDER BY name
            """), {"tenant_id": tenant_id})).mappings().all()
        return [{"id": row["id"], "name": row["name"]} for row in rows]
    except Exception as exc:
        logger.exception("Dashboard property lookup failed")
        raise HTTPException(status_code=503, detail="Property data is temporarily unavailable") from exc


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    current_user=Depends(get_current_user),
) -> Dict[str, Any]:
    tenant_id = tenant_for(current_user)
    if month and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
        raise HTTPException(status_code=422, detail="month must use YYYY-MM format")
    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id, month)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Dashboard revenue lookup failed")
        raise HTTPException(status_code=503, detail="Revenue data is temporarily unavailable") from exc
    if revenue_data.get("not_found"):
        raise HTTPException(status_code=404, detail="Property not found")
    return {
        "property_id": revenue_data["property_id"],
        "total_revenue": revenue_data["total"],
        "currency": revenue_data["currency"],
        "reservations_count": revenue_data["count"],
        "month": revenue_data["month"],
        "timezone": revenue_data["timezone"],
    }
