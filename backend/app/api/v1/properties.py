from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from ...core.auth import authenticate_request
from ...models.auth import AuthenticatedUser
from ...services.cache import get_tenant_properties

router = APIRouter()

@router.get("/properties")
async def get_properties(
    current_user: AuthenticatedUser = Depends(authenticate_request)
) -> List[Dict[str, Any]]:
    tenant_id = current_user.tenant_id

    try:
        return await get_tenant_properties(tenant_id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch properties: {str(e)}"
        )