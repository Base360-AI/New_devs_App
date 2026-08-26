"""
Minimal tenant resolver for authentication.
"""
from typing import Optional
import logging

from jose import jwt, JWTError

from ..config import settings

logger = logging.getLogger(__name__)


class TenantResolver:
    """Minimal tenant resolver that extracts tenant_id from JWT claims."""

    @staticmethod
    def resolve_tenant_from_token(token_payload: dict) -> Optional[str]:
        """
        Extract tenant_id from JWT token payload.

        Args:
            token_payload: Decoded JWT payload

        Returns:
            Tenant ID if found, None otherwise
        """
        # Try app_metadata first (server-controlled claims; this is where login.py puts it)
        app_metadata = token_payload.get('app_metadata') or {}
        tenant_id = app_metadata.get('tenant_id')
        if tenant_id:
            return tenant_id

        # Try user_metadata as fallback
        user_metadata = token_payload.get('user_metadata') or {}
        tenant_id = user_metadata.get('tenant_id')
        if tenant_id:
            return tenant_id

        # Try root level
        tenant_id = token_payload.get('tenant_id')
        if tenant_id:
            return tenant_id

        logger.warning("No tenant_id found in token payload")
        return None

    @staticmethod
    def resolve_tenant_from_user(user_data: dict) -> Optional[str]:
        """
        Extract tenant_id from user data.

        Args:
            user_data: User data dictionary

        Returns:
            Tenant ID if found, None otherwise
        """
        # Check various possible locations
        if 'tenant_id' in user_data:
            return user_data['tenant_id']

        if 'user_metadata' in user_data:
            tenant_id = user_data['user_metadata'].get('tenant_id')
            if tenant_id:
                return tenant_id

        if 'app_metadata' in user_data:
            tenant_id = user_data['app_metadata'].get('tenant_id')
            if tenant_id:
                return tenant_id

        return None

    # Known challenge accounts. Used only as a fallback when the token carries no claim.
    _EMAIL_TENANT_MAP = {
        "sunset@propertyflow.com": "tenant-a",
        "ocean@propertyflow.com": "tenant-b",
        "candidate@propertyflow.com": "tenant-a",
    }

    @staticmethod
    async def resolve_tenant_id(user_id: str, user_email: str, token: Optional[str] = None) -> Optional[str]:
        """
        Resolve tenant ID for a user.

        Order: signed JWT claim -> known account mapping -> None.

        BUG FIX: this used to return "tenant-a" for *any* unknown user, so any
        authenticated account that lacked a tenant silently became Sunset Properties.
        Unknown tenant must resolve to None and be rejected downstream (403).
        """
        if token:
            try:
                payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"], audience="authenticated")
                tenant_id = TenantResolver.resolve_tenant_from_token(payload)
                if tenant_id:
                    return tenant_id
            except JWTError:
                # Not one of our JWTs (e.g. a Supabase token) - fall through to the mapping.
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
