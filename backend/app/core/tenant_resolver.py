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
    async def resolve_tenant_id(
        user_id: str,
        user_email: str,
        token: Optional[str] = None,
        token_payload: Optional[dict] = None,
        user_data: Optional[dict] = None,
    ) -> Optional[str]:
        """
        Resolve the tenant for a request from its verified credential.

        This used to be a hardcoded email -> tenant table ending in
        `return "tenant-a"`, so every user it did not recognise was silently
        placed in Sunset Properties' tenant and served their data.

        Args:
            user_id: User ID
            user_email: User email, for logging only
            token: Unused; kept for call-site compatibility
            token_payload: Claims of the ALREADY VERIFIED token
            user_data: Identity-provider user record, as a fallback

        Returns:
            The tenant ID, or None when the credential carries none. Callers
            must treat None as "not authenticated", never as a default.
        """
        if token_payload:
            tenant_id = TenantResolver.resolve_tenant_from_token(token_payload)
            if tenant_id:
                return tenant_id

        if user_data:
            tenant_id = TenantResolver.resolve_tenant_from_user(user_data)
            if tenant_id:
                return tenant_id

        logger.warning(
            "No tenant_id on the credential presented by %s (id=%s)", user_email, user_id
        )
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
