from fastapi import APIRouter, Depends
from typing import Dict, Any, List
from app.services.properties import list_properties
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()


@router.get("/properties")
async def get_properties(
    current_user: dict = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """List the authenticated tenant's properties (for the dashboard selector)."""
    tenant_id = getattr(current_user, "tenant_id", "default_tenant") or "default_tenant"
    return await list_properties(tenant_id)
