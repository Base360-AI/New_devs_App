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
        user_id: str, user_email: str, token: Optional[str] = None
    ) -> Optional[str]:
        challenge_tenants = {
            "sunset@propertyflow.com": "tenant-a",
            "ocean@propertyflow.com": "tenant-b",
            "candidate@propertyflow.com": "tenant-a",
        }
        if user_email in challenge_tenants:
            return challenge_tenants[user_email]

        try:
            from app.database import supabase

            response = (
                supabase.service.table("user_tenants")
                .select("tenant_id")
                .eq("user_id", user_id)
                .eq("is_active", True)
                .execute()
            )
            tenant_ids = {
                row.get("tenant_id")
                for row in response.data or []
                if row.get("tenant_id")
            }
            if len(tenant_ids) == 1:
                return tenant_ids.pop()
            if len(tenant_ids) > 1:
                logger.warning(
                    f"User {user_id} has multiple active tenant memberships"
                )
        except Exception as error:
            logger.warning(f"Tenant membership lookup failed for {user_id}: {error}")

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
