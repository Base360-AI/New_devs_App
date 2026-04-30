"""Tenant resolver — derives tenant_id from JWT claims and user metadata.

A previous implementation hard-coded an email-to-tenant map with a default of
``tenant-a`` for any unknown user, which would have silently granted cross-tenant
access if a third user ever appeared. This version trusts only what the verified
JWT carries (or what's already on the user object) and refuses to make one up.
"""

import logging
from typing import Optional

import jwt

logger = logging.getLogger(__name__)


class TenantResolver:
    """Resolve tenant_id from JWT claims with no implicit fallbacks."""

    @staticmethod
    def resolve_tenant_from_token(token_payload: dict) -> Optional[str]:
        """Extract tenant_id from a decoded JWT payload."""
        for container in ("user_metadata", "app_metadata"):
            data = token_payload.get(container)
            if isinstance(data, dict) and data.get("tenant_id"):
                return data["tenant_id"]

        return token_payload.get("tenant_id")

    @staticmethod
    def resolve_tenant_from_user(user_data: dict) -> Optional[str]:
        """Extract tenant_id from a user-shaped dict."""
        if user_data.get("tenant_id"):
            return user_data["tenant_id"]

        for container in ("user_metadata", "app_metadata"):
            data = user_data.get(container)
            if isinstance(data, dict) and data.get("tenant_id"):
                return data["tenant_id"]

        return None

    @staticmethod
    async def resolve_tenant_id(
        user_id: str,
        user_email: str,
        token: Optional[str] = None,
    ) -> Optional[str]:
        """Resolve tenant_id from the JWT.

        Returns ``None`` when no tenant_id is present — the caller MUST treat
        a missing tenant as an authentication failure rather than substituting
        a default.
        """
        if token:
            try:
                # Signature is verified upstream by the auth layer; we only need
                # to read the claims here.
                payload = jwt.decode(token, options={"verify_signature": False})
                tenant_id = TenantResolver.resolve_tenant_from_token(payload)
                if tenant_id:
                    return tenant_id
            except jwt.PyJWTError as exc:
                logger.warning(
                    "Failed to decode token for tenant resolution (user=%s): %s",
                    user_email,
                    exc,
                )

        logger.warning(
            "No tenant_id resolvable for user %s (%s) — refusing to default",
            user_email,
            user_id,
        )
        return None

    @staticmethod
    async def update_user_tenant_metadata(user_id: str, tenant_id: str) -> None:
        """No-op: persistent metadata updates aren't supported in this resolver."""
        return None
