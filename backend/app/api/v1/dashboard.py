import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import authenticate_request
from app.models.auth import AuthenticatedUser
from app.services.cache import get_revenue_summary
from app.services.reservations import get_pool

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: AuthenticatedUser = Depends(authenticate_request),
):
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant is required")

    try:
        pool = await get_pool()
        async with pool.acquire() as connection:
            rows = await connection.fetch(
                """
                    SELECT p.id, p.name,
                           TO_CHAR(MAX(r.check_in_date AT TIME ZONE p.timezone), 'YYYY-MM') AS latest_month
                    FROM properties p
                    LEFT JOIN reservations r
                        ON r.property_id = p.id AND r.tenant_id = p.tenant_id
                    WHERE p.tenant_id = $1
                    GROUP BY p.id, p.name, p.tenant_id
                    ORDER BY p.name
                """,
                current_user.tenant_id,
            )
            return [dict(row) for row in rows]
    except Exception:
        logger.exception("Failed to load dashboard properties")
        raise HTTPException(status_code=503, detail="Dashboard data unavailable")


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: int = Query(ge=1, le=12),
    year: int = Query(ge=1, le=9999),
    current_user: AuthenticatedUser = Depends(authenticate_request),
) -> Dict[str, Any]:
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant is required")

    try:
        revenue_data = await get_revenue_summary(property_id, current_user.tenant_id, month, year)
    except LookupError:
        raise HTTPException(status_code=404, detail="Property not found")
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    except Exception:
        logger.exception("Failed to load dashboard summary")
        raise HTTPException(status_code=503, detail="Dashboard data unavailable")

    return {
        "property_id": revenue_data["property_id"],
        "total_revenue": revenue_data["total"],
        "currency": revenue_data["currency"],
        "reservations_count": revenue_data["count"],
    }
