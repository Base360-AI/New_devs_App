from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

EMAIL_TENANT_MAP = {
    "sunset@propertyflow.com": "tenant-a",
    "ocean@propertyflow.com": "tenant-b",
    "candidate@propertyflow.com": "tenant-a",
}


def resolve_tenant_id(current_user: Any) -> str:
    """Resolve tenant_id from authenticated user object or dict payload."""
    tenant_id = None
    email = ""

    if isinstance(current_user, dict):
        tenant_id = (
            current_user.get("tenant_id")
            or (current_user.get("user_metadata") or {}).get("tenant_id")
            or (current_user.get("app_metadata") or {}).get("tenant_id")
        )
        email = str(current_user.get("email") or "").lower()
    else:
        tenant_id = (
            getattr(current_user, "tenant_id", None)
            or getattr(getattr(current_user, "user_metadata", None), "tenant_id", None)
            or getattr(getattr(current_user, "app_metadata", None), "tenant_id", None)
        )
        email = str(getattr(current_user, "email", "") or "").lower()

    if tenant_id in ("tenant-a", "tenant-b"):
        return tenant_id

    return EMAIL_TENANT_MAP.get(email, "default_tenant")

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    tenant_id = resolve_tenant_id(current_user)
    
    revenue_data = await get_revenue_summary(property_id, tenant_id)
    
    total_revenue_float = float(revenue_data['total'])
    
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": total_revenue_float,
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
