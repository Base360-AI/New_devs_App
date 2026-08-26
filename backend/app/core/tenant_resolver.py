"""
Minimal tenant resolver for authentication.
"""
import logging
from typing import Optional, Sequence

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
        # app_metadata is signed and server-controlled. user_metadata is not
        # authoritative because users may be able to edit it themselves.
        if "app_metadata" in token_payload:
            tenant_id = token_payload["app_metadata"].get("tenant_id")
            if tenant_id:
                return tenant_id

        logger.warning("No tenant_id found in signed app_metadata")
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
        if "app_metadata" in user_data:
            tenant_id = user_data["app_metadata"].get("tenant_id")
            if tenant_id:
                return tenant_id

        return None

    @staticmethod
    async def resolve_tenant_id(
        user_id: str,
        user_email: str,
        token_payload: Optional[dict] = None,
        membership_tenant_ids: Optional[Sequence[str]] = None,
    ) -> Optional[str]:
        """
        Resolve tenant ID for a user.
        
        Args:
            user_id: User ID
            user_email: User email
            
        Returns:
            Tenant ID, or None when no authoritative assignment exists.
        """
        if token_payload:
            tenant_id = TenantResolver.resolve_tenant_from_token(token_payload)
            if tenant_id:
                return tenant_id

        tenant_ids = [
            tenant_id for tenant_id in membership_tenant_ids or [] if tenant_id
        ]
        if len(tenant_ids) == 1:
            return tenant_ids[0]

        logger.warning(
            "Unable to resolve one tenant for user %s (%s)",
            user_email,
            user_id,
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
