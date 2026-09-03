"""Shared tenant-ownership checks for service-role user operations."""

from fastapi import HTTPException, status

from ..database import supabase
from ..models.auth import AuthenticatedUser


def require_user_in_operator_tenant(
    operator: AuthenticatedUser, target_user_id: str
) -> str:
    """Return the tenant ID or hide a cross-tenant target behind a 404."""
    tenant_id = operator.tenant_id
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active tenant membership",
        )

    if target_user_id == operator.id:
        return tenant_id

    membership = (
        supabase.service.table("user_tenants")
        .select("tenant_id")
        .eq("user_id", target_user_id)
        .eq("tenant_id", tenant_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if not membership.data:
        # Do not disclose that an identifier exists in a different tenant.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return tenant_id
