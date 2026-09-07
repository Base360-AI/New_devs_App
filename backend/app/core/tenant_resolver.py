"""
Minimal tenant resolver for authentication.
"""
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class TenantResolver:
    """Minimal tenant resolver that extracts tenant_id from JWT claims."""

    @staticmethod
    def resolve_tenant_from_token(token_payload: dict) -> Optional[str]:
        """Extract tenant_id from JWT token payload."""
        # Try app_metadata first (server-controlled claims)
        app_metadata = token_payload.get('app_metadata') or {}
        tenant_id = app_metadata.get('tenant_id')
        if tenant_id:
            return tenant_id

        # Try user_metadata
        user_metadata = token_payload.get('user_metadata') or {}
        tenant_id = user_metadata.get('tenant_id')
        if tenant_id:
            return tenant_id

        # Try root level
        tenant_id = token_payload.get('tenant_id')
        if tenant_id:
            return tenant_id

        return None

    @staticmethod
    def resolve_tenant_from_user(user_data: dict) -> Optional[str]:
        """Extract tenant_id from user data."""
        if 'app_metadata' in user_data:
            tenant_id = user_data['app_metadata'].get('tenant_id')
            if tenant_id:
                return tenant_id

        if 'user_metadata' in user_data:
            tenant_id = user_data['user_metadata'].get('tenant_id')
            if tenant_id:
                return tenant_id

        if 'tenant_id' in user_data:
            return user_data['tenant_id']

        return None

    _EMAIL_TENANT_MAP = {
        "sunset@propertyflow.com": "tenant-a",
        "ocean@propertyflow.com": "tenant-b",
        "candidate@propertyflow.com": "tenant-a",
    }

    @staticmethod
    async def resolve_tenant_id(user_id: str, user_email: str, token: Optional[str] = None) -> Optional[str]:
        """
        Resolve tenant ID for a user.
        Order: JWT claims -> known email mapping -> None.
        Does NOT default unknown users to 'tenant-a'.
        """
        if token:
            try:
                from jose import jwt
                from ..config import settings
                payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"], options={"verify_exp": False})
                tenant_id = TenantResolver.resolve_tenant_from_token(payload)
                if tenant_id:
                    return tenant_id
            except Exception:
                pass

        tenant_id = TenantResolver._EMAIL_TENANT_MAP.get((user_email or "").lower())
        if tenant_id:
            return tenant_id

        logger.warning(f"Could not resolve tenant for user {user_email} ({user_id})")
        return None

    @staticmethod
    async def update_user_tenant_metadata(user_id: str, tenant_id: str) -> None:
        """
        Update user metadata with tenant_id.
        
        Args:
            user_id: User ID
            tenant_id: Tenant ID
        """
        # No-op in this resolver implementation.
        pass
