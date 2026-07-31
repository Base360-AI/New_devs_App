from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, Optional
from decimal import Decimal, ROUND_HALF_UP
from app.services.cache import get_revenue_summary
from app.services.reservations import (
    calculate_monthly_revenue,
    DatabaseUnavailableError,
)
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()


def _money_string(value) -> str:
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return format(amount, "f")


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:

    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"

    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id)
    except DatabaseUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    response: Dict[str, Any] = {
        "property_id": revenue_data["property_id"],
        "tenant_id": tenant_id,
        "total_revenue": _money_string(revenue_data["total"]),
        "currency": revenue_data["currency"],
        "reservations_count": revenue_data["count"],
    }

    if month is not None and year is not None:
        try:
            monthly = await calculate_monthly_revenue(
                property_id=property_id,
                month=month,
                year=year,
                tenant_id=tenant_id,
            )
        except DatabaseUnavailableError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e

        response["monthly_revenue"] = _money_string(monthly)
        response["month"] = month
        response["year"] = year

    return response
