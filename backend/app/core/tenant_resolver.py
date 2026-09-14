"""Resolve tenants from server-controlled, verified identity metadata."""
from typing import Optional


class TenantResolver:
    @staticmethod
    def resolve_tenant_from_token(token_payload: dict) -> Optional[str]:
        """Caller must verify the token before passing its claims."""
        tenant_id = (token_payload.get("app_metadata") or {}).get("tenant_id") or token_payload.get("tenant_id")
        return tenant_id if isinstance(tenant_id, str) and tenant_id.strip() else None

    @staticmethod
    def resolve_tenant_from_user(user_data: dict) -> Optional[str]:
        # user_metadata is editable by the user and cannot grant tenant access.
        return TenantResolver.resolve_tenant_from_token(user_data)

    @staticmethod
    async def resolve_tenant_id(user_id: str, user_email: str, token: Optional[str] = None) -> Optional[str]:
        from ..database import supabase

        response = supabase.auth.get_user(token) if token else supabase.auth.admin.get_user_by_id(user_id)
        user = getattr(response, "user", None)
        if user is None or user.id != user_id:
            return None
        return TenantResolver.resolve_tenant_from_user({
            "tenant_id": getattr(user, "tenant_id", None),
            "app_metadata": getattr(user, "app_metadata", None),
        })

    @staticmethod
    async def update_user_tenant_metadata(user_id: str, tenant_id: str) -> None:
        pass
