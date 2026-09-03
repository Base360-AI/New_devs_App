import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr

from ...config import settings
from ...core.auth import authenticate_request, invalidate_user_cache
from ...core.security import (
    authenticate_local_user,
    create_access_token,
    decode_access_token,
    login_rate_limiter,
    revoke_access_token,
)
from ...core.tenant_resolver import TenantResolver
from ...database import supabase
from ...models.auth import AuthenticatedUser


router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]
    error: Optional[str] = None


def _invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, http_request: Request):
    """Authenticate either a supplied demo account or a configured Supabase user."""
    email = request.email.lower().strip()
    client_ip = http_request.client.host if http_request.client else "unknown"

    if login_rate_limiter.is_blocked(email, client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again shortly.",
            headers={"Retry-After": str(login_rate_limiter.window_seconds)},
        )

    logger.info("Login attempt")

    # With no external identity service configured, keep the two accounts from
    # ASSIGNMENT.md available through constant-time hash verification.
    if not settings.supabase_url or not settings.supabase_service_role_key:
        local_user = authenticate_local_user(email, request.password)
        if not local_user:
            login_rate_limiter.record_failure(email, client_ip)
            logger.warning("Rejected local login")
            raise _invalid_credentials()

        login_rate_limiter.record_success(email, client_ip)
        return LoginResponse(
            access_token=create_access_token(local_user),
            user={
                "id": local_user.id,
                "email": local_user.email,
                "name": local_user.name,
                "is_admin": local_user.role == "admin",
                "tenant_id": local_user.tenant_id,
                "permissions": [],
                "cities": [],
            },
        )

    # In configured environments, let the identity provider verify the actual
    # password. Listing users is not authentication.
    try:
        auth_response = supabase.auth.sign_in_with_password(
            {"email": email, "password": request.password}
        )
        authenticated_user = getattr(auth_response, "user", None)
        session = getattr(auth_response, "session", None)
        access_token = getattr(session, "access_token", None)
        if not authenticated_user or not access_token:
            raise _invalid_credentials()
    except HTTPException:
        login_rate_limiter.record_failure(email, client_ip)
        raise
    except Exception:
        login_rate_limiter.record_failure(email, client_ip)
        logger.warning("Identity provider rejected login")
        raise _invalid_credentials()

    login_rate_limiter.record_success(email, client_ip)
    permissions = []
    cities = []
    try:
        permissions_response = (
            supabase.service.table("user_permissions")
            .select("section, action")
            .eq("user_id", authenticated_user.id)
            .execute()
        )
        permissions = permissions_response.data or []
        cities_response = (
            supabase.service.table("users_city")
            .select("city_name")
            .eq("user_id", authenticated_user.id)
            .execute()
        )
        cities = [
            row["city_name"].lower()
            for row in (cities_response.data or [])
            if row.get("city_name")
        ]
    except Exception as exc:
        logger.warning("Login metadata lookup failed: %s", type(exc).__name__)

    metadata = authenticated_user.app_metadata or {}
    tenant_id = await TenantResolver.resolve_tenant_id(
        user_id=authenticated_user.id,
        user_email=authenticated_user.email,
    )
    if not tenant_id:
        logger.warning("Authenticated user has no active tenant")
        raise HTTPException(status_code=403, detail="No active tenant membership")

    return LoginResponse(
        access_token=access_token,
        user={
            "id": authenticated_user.id,
            "email": authenticated_user.email,
            "name": (authenticated_user.user_metadata or {}).get(
                "name", authenticated_user.email.split("@")[0]
            ),
            "is_admin": metadata.get("role") == "admin",
            "tenant_id": tenant_id,
            "permissions": permissions,
            "cities": cities,
        },
    )


@router.post("/logout")
async def logout(
    request: Request,
    user: AuthenticatedUser = Depends(authenticate_request),
):
    """Invalidate the current local token and clear its cached identity."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            revoke_access_token(decode_access_token(token))
        except Exception:
            # Supabase tokens are revoked by the provider/client; there is no
            # local JTI to add to the demo denylist.
            pass
    invalidate_user_cache(user.id)
    return {"message": "Logged out successfully"}
