from fastapi import APIRouter, Depends, HTTPException
from typing import Any, Dict, List
from app.services.cache import get_revenue_summary
from app.services.reservations import REPORT_MONTH, REPORT_YEAR, list_tenant_properties
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()


def _tenant_id(current_user) -> str:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant not resolved")
    return tenant_id


@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    return await list_tenant_properties(_tenant_id(current_user))


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    year: int = REPORT_YEAR,
    month: int = REPORT_MONTH,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant_id = _tenant_id(current_user)
    revenue_data = await get_revenue_summary(property_id, tenant_id, year=year, month=month)

    return {
        "property_id": revenue_data["property_id"],
        "total_revenue": revenue_data["total"],
        "currency": revenue_data["currency"],
        "reservations_count": revenue_data["count"],
    }
