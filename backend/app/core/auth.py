from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from typing import Optional, List
from datetime import datetime
import logging
import hashlib
import asyncio
from ..database import supabase
from ..models.auth import AuthenticatedUser, Permission
from .tenant_resolver import TenantResolver
from .security import decode_access_token, is_access_token_revoked

logger = logging.getLogger(__name__)

# Use non-throwing bearer so we can return consistent 401s
security = HTTPBearer(auto_error=False)

# Authentication cache to prevent multiple DB calls for same token
auth_cache = {}
CACHE_DURATION = 1800  # 30 minutes (increased from 5 minutes for better performance)


def clear_auth_cache():
    """Clear authentication cache"""
    global auth_cache
    auth_cache = {}


def invalidate_user_cache(user_id: str):
    """Invalidate all cached authentication entries for a specific user

    Args:
        user_id: The user ID whose cache entries should be cleared

    Returns:
        int: Number of cache entries cleared
    """
    global auth_cache

    # Find all token hashes for this user
    keys_to_delete = []
    for token_hash, cached_data in auth_cache.items():
        if cached_data.get("user") and cached_data["user"].id == user_id:
            keys_to_delete.append(token_hash)

    # Delete found entries
    for key in keys_to_delete:
        del auth_cache[key]

    if keys_to_delete:
        logger.info("Invalidated %d authentication cache entries", len(keys_to_delete))

    return len(keys_to_delete)


async def authenticate_request(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> AuthenticatedUser:
    """Authenticate user from JWT token with caching to prevent duplicate API calls"""
    start_time = datetime.now()

    # Handle missing Authorization header or malformed scheme
    if credentials is None or not getattr(credentials, "credentials", None):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    token = credentials.credentials
    # Create cache key from token hash (more secure than storing full token)
    token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]

    # Check cache first
    if token_hash in auth_cache:
        cached_data = auth_cache[token_hash]
        if datetime.now().timestamp() - cached_data["timestamp"] < CACHE_DURATION:
            cached_user = cached_data["user"]
            # If not, force a refresh to get proper tenant isolation
            if not cached_user.tenant_id:
                logger.warning("AUTH: Cached identity missing tenant_id; forcing refresh")
                del auth_cache[token_hash]
            else:
                logger.debug("AUTH: Using cached authentication")
                return cached_user
        else:
            # Remove expired cache entry
            del auth_cache[token_hash]

    logger.debug("AUTH: Starting authentication")

    try:
        logger.debug("AUTH: Verifying token")

        # Verify token - handle both Supabase tokens and custom JWT tokens
        local_payload = None
        try:
            # First try to decode as a custom JWT token.
            try:
                local_payload = decode_access_token(token)
                if is_access_token_revoked(local_payload):
                    raise jwt.InvalidTokenError("Token has been revoked")
                logger.debug("AUTH: Successfully decoded local JWT")
                
                # Create a mock user object from JWT payload
                class MockUser:
                    def __init__(self, payload):
                        self.id = payload.get('sub')
                        self.email = payload.get('email')
                        self.app_metadata = payload.get('app_metadata', {})
                        self.user_metadata = payload.get('user_metadata', {})
                        self.raw_app_metadata = payload.get('app_metadata', {})
                        
                user = MockUser(local_payload)
                
            except jwt.InvalidTokenError:
                # If custom JWT fails, try Supabase auth
                response = supabase.auth.get_user(token)
                user = response.user
                
        except Exception as e:
            # Malformed or invalid token (e.g., wrong number of segments)
            logger.warning("AUTH: Token verification failed: %s", e.__class__.__name__)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing token",
            )

        logger.debug("AUTH: Identity provider returned user=%s", bool(user))

        if not user:
            logger.warning("AUTH: No user found for provided token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )

        # Get user permissions.
        logger.debug("AUTH: Fetching permissions")
        try:
            permissions_response = (
                supabase.service.table("user_permissions").select("section, action").eq("user_id", user.id).execute()
            )
            permissions = [Permission(**perm) for perm in permissions_response.data]
        except Exception as e:
            # Use empty permissions when permissions cannot be fetched.
            logger.debug("AUTH: Using empty permissions")
            permissions = []
        logger.debug("AUTH: Found %d permissions", len(permissions))

        # Get user cities.
        logger.debug("AUTH: Fetching city assignments")
        try:
            cities_response = supabase.service.table("users_city").select("city_name").eq("user_id", user.id).execute()
            # Ensure cities are always lowercase for consistency
            user_cities = [city["city_name"].lower() for city in cities_response.data if city.get("city_name")]
        except Exception as e:
            # Use empty cities when city assignments cannot be fetched.
            logger.debug("AUTH: Using empty city assignments")
            user_cities = []
        logger.debug("AUTH: Found %d city assignments", len(user_cities))

        # Determine tenant role for admin fallback.
        tenant_role = None
        tenant_ids: List[str] = []
        try:
            tenant_role_response = (
                supabase.service.table("user_tenants")
                .select("tenant_id, role")
                .eq("user_id", user.id)
                .eq("is_active", True)
                .execute()
            )
            if tenant_role_response.data:
                tenant_ids = [row.get("tenant_id") for row in tenant_role_response.data if row.get("tenant_id")]
                for row in tenant_role_response.data:
                    role_value = row.get("role")
                    if role_value:
                        tenant_role = role_value
                    if role_value in ("admin", "owner"):
                        tenant_role = role_value
                        break
        except Exception as tenant_role_error:
            logger.debug("AUTH: Using token tenant role")
            tenant_role = getattr(user, 'app_metadata', {}).get('role', 'user')

        # Check if user is admin
        # Check both app_metadata and raw_app_metadata for the role
        role = None
        if hasattr(user, "raw_app_metadata") and user.raw_app_metadata:
            role = user.raw_app_metadata.get("role")
        elif hasattr(user, "app_metadata") and user.app_metadata:
            role = user.app_metadata.get("role")

        is_admin = role in ("admin", "owner") or tenant_role in ("admin", "owner")
        logger.debug("AUTH: Administrator status: %s", is_admin)

        allowed_city_map = {}
        if not tenant_ids and getattr(user, "tenant_id", None):
            tenant_ids = [user.tenant_id]

        if tenant_ids:
            try:
                result = (
                    supabase.service.table("all_properties")
                    .select("city")
                    .in_("tenant_id", tenant_ids)
                    .eq("status", "active")
                    .execute()
                )
                for row in result.data or []:
                    city = (row.get("city") or "").strip()
                    if not city:
                        continue
                    key = city.lower()
                    if key not in allowed_city_map:
                        allowed_city_map[key] = city
            except Exception:
                logger.debug("AUTH: No property-derived cities available")
                allowed_city_map = {}

        # ✅ SIMPLIFIED: Let endpoint-specific logic handle admin vs user city differences
        # Auth only provides initial user city assignments for ALL users
        # Admin city logic is handled in individual endpoints (city_access_fast.py)
        logger.debug("AUTH: City access will be determined by endpoint logic")

        # Use TenantResolver for comprehensive tenant resolution
        tenant_id = (
            local_payload.get("tenant_id")
            if local_payload
            else await TenantResolver.resolve_tenant_id(
                token=token, user_id=user.id, user_email=user.email
            )
        )
        if not tenant_id:
            logger.warning("AUTH: Authenticated user has no active tenant")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No active tenant membership",
            )

        # If we found a tenant_id and it's not in the user's metadata, update it for next time
        current_tenant_in_metadata = None
        if hasattr(user, "raw_app_metadata") and user.raw_app_metadata:
            current_tenant_in_metadata = user.raw_app_metadata.get("tenant_id")
        elif hasattr(user, "app_metadata") and user.app_metadata:
            current_tenant_in_metadata = user.app_metadata.get("tenant_id")

        if tenant_id and current_tenant_in_metadata != tenant_id:
            logger.debug("AUTH: Updating tenant metadata")
            asyncio.create_task(TenantResolver.update_user_tenant_metadata(user.id, tenant_id))

        auth_user = AuthenticatedUser(
            id=user.id,
            email=user.email,
            permissions=permissions,
            cities=user_cities,
            is_admin=is_admin,
            tenant_id=tenant_id,
        )

        # Cache the authentication result
        auth_cache[token_hash] = {
            "user": auth_user,
            "timestamp": datetime.now().timestamp(),
        }

        # Clean up old cache entries (keep cache size manageable)
        current_time = datetime.now().timestamp()
        expired_keys = [k for k, v in auth_cache.items() if current_time - v["timestamp"] > CACHE_DURATION]
        for key in expired_keys:
            del auth_cache[key]

        duration = (datetime.now() - start_time).total_seconds()
        logger.info(
            "AUTH: OK in %.2fs, cities=%d, permissions=%d",
            duration,
            len(user_cities),
            len(permissions),
        )

        return auth_user

    except Exception as error:
        duration = (datetime.now() - start_time).total_seconds()
        # If we raised HTTPException above, rethrow
        if isinstance(error, HTTPException):
            raise
        logger.warning("AUTH: Failed (%s) in %.2fs", type(error).__name__, duration)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
        )


def has_permission(user: AuthenticatedUser, section: str, action: str) -> bool:
    """Check if user has specific permission"""
    logger.debug("Permission check for %s.%s; admin=%s", section, action, user.is_admin)
    if user.is_admin:
        logger.debug("Administrator permission granted")
        return True

    # Check for permission with wildcard support (matching frontend logic)
    # Also check for all_reservations when checking for reservations
    has_perm = any(
        (
            (
                p.section == section
                or p.section == "*"
                or (section == "reservations" and p.section == "all_reservations")
            )
            and (p.action == action or p.action == "*")
        )
        for p in user.permissions
    )

    if has_perm:
        logger.debug("Permission granted for %s.%s", section, action)
    else:
        logger.debug("Permission denied for %s.%s", section, action)

    return has_perm


def require_permission(section: str, action: str):
    """Dependency to require specific permission"""

    def permission_checker(user: AuthenticatedUser = Depends(authenticate_request)):
        if not has_permission(user, section, action):
            logger.warning("Permission denied; required=%s.%s", section, action)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions: {section}.{action}",
            )
        return user

    return permission_checker


def require_admin(
    user: AuthenticatedUser = Depends(authenticate_request),
) -> AuthenticatedUser:
    """Require an authenticated tenant administrator."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )
    return user


def require_any_permission(*permissions):
    """Dependency to require any of the specified permissions (OR logic)
    
    Args:
        *permissions: List of tuples (section, action) representing permissions
    
    Example:
        require_any_permission(
            ("guest_portal", "read"),
            ("lockbox", "create"), 
            ("internal_keys", "create")
        )
    """
    def permission_checker(user: AuthenticatedUser = Depends(authenticate_request)):
        # Check if user has any of the required permissions
        has_any_permission = any(
            has_permission(user, section, action) 
            for section, action in permissions
        )
        
        if not has_any_permission:
            permission_strings = [f"{section}.{action}" for section, action in permissions]
            logger.warning("Permission denied; required_any=%s", permission_strings)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions: requires any of {permission_strings}",
            )
        
        # Log which permission was matched for debugging
        matched_permissions = [
            f"{section}.{action}" for section, action in permissions
            if has_permission(user, section, action)
        ]
        logger.debug("Permission granted via %s", matched_permissions)
        
        return user

    return permission_checker


def clear_auth_cache():
    """Clear the authentication cache - useful for debugging tenant issues"""
    global auth_cache
    old_size = len(auth_cache)
    auth_cache.clear()
    logger.info(f"Cleared authentication cache - removed {old_size} entries")
    return old_size


async def verify_token_ws(token: str) -> Optional[AuthenticatedUser]:
    """Verify JWT token for WebSocket connections using same approach as regular authentication"""
    try:
        logger.debug("WS_AUTH: Verifying WebSocket token")

        local_payload = None
        try:
            local_payload = decode_access_token(token)
            if is_access_token_revoked(local_payload):
                return None

            class LocalTokenUser:
                def __init__(self, payload):
                    self.id = payload.get("sub")
                    self.email = payload.get("email")
                    self.app_metadata = payload.get("app_metadata", {})
                    self.raw_app_metadata = self.app_metadata

            user = LocalTokenUser(local_payload)
        except Exception as e:
            try:
                response = supabase.auth.get_user(token)
                user = response.user
            except Exception:
                logger.warning(f"WS_AUTH: Token verification failed: {e.__class__.__name__}")
                return None

        if not user:
            logger.warning("WS_AUTH: No user found for provided token")
            return None

        # Get user permissions (same as regular auth)
        logger.debug("WS_AUTH: Fetching permissions")
        permissions_response = (
            supabase.service.table("user_permissions").select("section, action").eq("user_id", user.id).execute()
        )
        permissions = [Permission(**perm) for perm in permissions_response.data]

        # Get user cities (same table name as regular auth)
        logger.debug("WS_AUTH: Fetching city assignments")
        cities_response = supabase.service.table("users_city").select("city_name").eq("user_id", user.id).execute()
        # Ensure cities are always lowercase for consistency (same as regular auth)
        user_cities = [city["city_name"].lower() for city in cities_response.data if city.get("city_name")]

        # Determine tenant role for admin fallback (same as regular auth)
        tenant_role = None
        tenant_ids = []
        try:
            tenant_role_response = (
                supabase.service.table("user_tenants")
                .select("tenant_id, role")
                .eq("user_id", user.id)
                .eq("is_active", True)
                .execute()
            )
            if tenant_role_response.data:
                tenant_ids = [row.get("tenant_id") for row in tenant_role_response.data if row.get("tenant_id")]
                for row in tenant_role_response.data:
                    role_value = row.get("role")
                    if role_value:
                        tenant_role = role_value
                    if role_value in ("admin", "owner"):
                        tenant_role = role_value
                        break
        except Exception as tenant_role_error:
            logger.warning("WS_AUTH: Failed to fetch tenant role: %s", type(tenant_role_error).__name__)

        # Check if user is admin (same logic as regular auth)
        role = None
        if hasattr(user, "raw_app_metadata") and user.raw_app_metadata:
            role = user.raw_app_metadata.get("role")
        elif hasattr(user, "app_metadata") and user.app_metadata:
            role = user.app_metadata.get("role")

        is_admin = role in ("admin", "owner") or tenant_role in ("admin", "owner")

        # Get allowed cities (same logic as regular auth)
        allowed_city_map = {}
        if not tenant_ids and getattr(user, "tenant_id", None):
            tenant_ids = [user.tenant_id]

        if tenant_ids:
            try:
                result = (
                    supabase.service.table("all_properties")
                    .select("city")
                    .in_("tenant_id", tenant_ids)
                    .eq("status", "active")
                    .execute()
                )
                for row in result.data or []:
                    city = (row.get("city") or "").strip()
                    if not city:
                        continue
                    key = city.lower()
                    if key not in allowed_city_map:
                        allowed_city_map[key] = city
            except Exception as allowed_error:
                logger.warning("WS_AUTH: Failed to resolve allowed cities: %s", type(allowed_error).__name__)

        # when no active properties exist in those cities. Users explicitly assigned
        # to cities in users_city table should keep that access regardless of properties.

        # Admin users get access to all cities from properties (same as regular auth)
        if is_admin:
            if allowed_city_map:
                user_cities = list(allowed_city_map.values())
                logger.debug("WS_AUTH: Administrator received %d property cities", len(user_cities))
            else:
                # Keep user's explicitly assigned cities even if no properties exist
                logger.debug("WS_AUTH: Administrator kept assigned cities")
        
        logger.debug("WS_AUTH: Final city count: %d", len(user_cities))

        # Use the comprehensive tenant resolver (same as regular auth)
        logger.debug("WS_AUTH: Resolving tenant")
        tenant_id = (
            local_payload.get("tenant_id")
            if local_payload
            else await TenantResolver.resolve_tenant_id(
                token=token, user_id=user.id, user_email=user.email
            )
        )
        if not tenant_id:
            return None

        auth_user = AuthenticatedUser(
            id=user.id,
            email=user.email,
            permissions=permissions,
            cities=user_cities,
            is_admin=is_admin,
            tenant_id=tenant_id,
        )

        logger.info(
            "WS_AUTH: Success; cities=%d, permissions=%d",
            len(user_cities),
            len(permissions),
        )
        return auth_user

    except Exception as e:
        logger.error("WS_AUTH: Failed (%s)", type(e).__name__)
        return None
