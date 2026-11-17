"""
Minimal tenant resolver for authentication.
"""
from typing import Optional
import logging

from jose import JWTError, jwt

logger = logging.getLogger(__name__)

# Seeded demo users and the tenant each one belongs to
KNOWN_USER_TENANTS = {
    "sunset@propertyflow.com": "tenant-a",
    "ocean@propertyflow.com": "tenant-b",
    "candidate@propertyflow.com": "tenant-a",
}


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
        # Try user_metadata first (most common location)
        if 'user_metadata' in token_payload:
            tenant_id = token_payload['user_metadata'].get('tenant_id')
            if tenant_id:
                return tenant_id

        # Try app_metadata as fallback
        if 'app_metadata' in token_payload:
            tenant_id = token_payload['app_metadata'].get('tenant_id')
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

    @staticmethod
    def _tenant_from_claims(token: str) -> Optional[str]:
        """
        Read tenant_id from a token that the caller has already verified.

        Only server-controlled locations are trusted (app_metadata and the
        root claim). user_metadata is editable by the user themselves, so it
        must never decide which tenant's data they can see.
        """
        try:
            claims = jwt.get_unverified_claims(token)
        except JWTError:
            return None
        app_metadata = claims.get("app_metadata") or {}
        return app_metadata.get("tenant_id") or claims.get("tenant_id")

    @staticmethod
    async def resolve_tenant_id(user_id: str, user_email: str, token: Optional[str] = None) -> Optional[str]:
        """
        Resolve tenant ID for a user.

        Args:
            user_id: User ID
            user_email: User email
            token: Verified access token, when available

        Returns:
            Tenant ID, or None when the user has no tenant. There is
            deliberately no default tenant: an unknown user must not be
            given another company's data.
        """
        if token:
            tenant_id = TenantResolver._tenant_from_claims(token)
            if tenant_id:
                return tenant_id

        # Fallback mapping by known user email.
        tenant_id = KNOWN_USER_TENANTS.get((user_email or "").lower())
        if not tenant_id:
            logger.warning(f"No tenant found for user {user_email} ({user_id})")
        return tenant_id

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
