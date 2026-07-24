from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, List
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user
from app.models.auth import AuthenticatedUser
import logging
from app.config import settings
import asyncpg
from datetime import datetime, timezone

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    timestamp: int = Query(..., alias="_t"),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    
    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"
    requested_date = datetime.fromtimestamp(
        timestamp / 1000,
        tz=timezone.utc,
    )
    year = requested_date.year
    month = requested_date.month
    
    revenue_data = await get_revenue_summary(property_id, tenant_id, year, month)
    
    # total_revenue_float = float(revenue_data['total'])
    
    return {
        "property_id": revenue_data['property_id'],
        # "total_revenue": total_revenue_float,
        "total_revenue": revenue_data['total'],
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }

@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: AuthenticatedUser  = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """
    Return only properties belonging to the authenticated user's tenant.
    """

    tenant_id = current_user.tenant_id

    if not tenant_id:
        raise HTTPException(
            status_code=403,
            detail="Authenticated user has no tenant",
        )

    connection = None

    try:
        connection = await asyncpg.connect(settings.database_url)

        rows = await connection.fetch(
            """
            SELECT
                id,
                name,
                timezone
            FROM properties
            WHERE tenant_id = $1
            ORDER BY name
            """,
            tenant_id,
        )

        return [
            {
                "id": row["id"],
                "name": row["name"],
                "timezone": row["timezone"],
            }
            for row in rows
        ]

    except Exception:
        logger.exception(
            "Failed to load properties for tenant %s",
            tenant_id,
        )

        raise HTTPException(
            status_code=503,
            detail="Properties are temporarily unavailable",
        )

    finally:
        if connection is not None:
            await connection.close()