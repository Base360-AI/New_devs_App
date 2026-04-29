from importlib import import_module
from typing import Dict, Any
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

fastapi = import_module("fastapi")
APIRouter = fastapi.APIRouter
Depends = fastapi.Depends
HTTPException = fastapi.HTTPException
Query = fastapi.Query

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: int | None = Query(default=None, ge=1, le=12),
    year: int | None = Query(default=None, ge=2000, le=2100),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:

    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    if (month is None) != (year is None):
        raise HTTPException(status_code=422, detail="month and year must be provided together")

    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id, month=month, year=year)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": revenue_data['total'],
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count'],
        "period_month": revenue_data['period_month'],
        "period_year": revenue_data['period_year'],
        "timezone": revenue_data['timezone'],
    }
