from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import authenticate_request as get_current_user
from app.services.cache import get_revenue_summary

router = APIRouter()


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = Query(
        None, ge=1, le=12, description="Calendar month (1-12). Defaults to current month."
    ),
    year: Optional[int] = Query(
        None, ge=2000, le=2100, description="Calendar year. Defaults to current year."
    ),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"

    # Default to the current calendar month when caller doesn't specify one.
    now = datetime.utcnow()
    effective_month = month if month is not None else now.month
    effective_year = year if year is not None else now.year

    try:
        revenue_data = await get_revenue_summary(
            property_id, tenant_id, effective_month, effective_year
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Keep revenue as a precise decimal string. Converting to float here
    # silently truncates NUMERIC(10,3) values into binary doubles and was
    # the source of the totals that were "off by a few cents".
    return {
        "property_id": revenue_data["property_id"],
        "total_revenue": revenue_data["total"],
        "currency": revenue_data["currency"],
        "reservations_count": revenue_data["count"],
        "month": revenue_data.get("month", effective_month),
        "year": revenue_data.get("year", effective_year),
    }
