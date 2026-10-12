from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List
from app.services.cache import get_revenue_summary
from app.services.reservations import list_tenant_properties
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()


def _tenant_id(current_user) -> str:
    # authenticate_request already rejects users without a tenant; this guards new callers.
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="No tenant assigned")
    return tenant_id


@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: dict = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    try:
        return await list_tenant_properties(_tenant_id(current_user))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Revenue data temporarily unavailable")


@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:

    tenant_id = _tenant_id(current_user)

    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id)
    except LookupError:
        # 404 (not 403) so other tenants' property IDs are not confirmed to exist
        raise HTTPException(status_code=404, detail="Property not found")
    except Exception:
        raise HTTPException(status_code=503, detail="Revenue data temporarily unavailable")

    total_revenue_float = float(revenue_data['total'])

    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": total_revenue_float,
        "currency": revenue_data['currency'],
        "tenant_id": tenant_id,
        "reservations_count": revenue_data['count']
    }
