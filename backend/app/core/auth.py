from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from typing import Optional, List
from datetime import datetime
import logging
import hashlib
import asyncio
from ..database import supabase
from ..models.auth import AuthenticatedUser, Permission
from ..config import settings
from .tenant_resolver import TenantResolver

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
        logger.info(f"Invalidated {len(keys_to_delete)} cache entries for user {user_id}")

    return len(keys_to_delete)


ADMIN_EMAILS = [
    "sid@theflexliving.com",
    "raouf@theflexliving.com",
    "michael@theflexliving.com",
    "younes@gmail.com",
    "yazid@theflexliving.com",
]


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
        is_cache_fresh = datetime.now().timestamp() - cached_data["timestamp"] < CACHE_DURATION
        token_exp = cached_data.get("exp")
        is_token_unexpired = token_exp is None or datetime.utcnow().timestamp() < token_exp

        if is_cache_fresh and is_token_unexpired:
            cached_user = cached_data["user"]
            # If not, force a refresh to get proper tenant isolation
            if not cached_user.tenant_id:
                logger.warning(f"AUTH: Cached auth for {cached_user.email} missing tenant_id - forcing refresh")
                del auth_cache[token_hash]
            else:
                logger.info(
                    f"AUTH: Using cached authentication for token {token_hash} (tenant: {cached_user.tenant_id}) for user: {cached_user.email}"
                )
                return cached_user
        else:
            logger.info(f"AUTH: Token cache expired or token payload exp passed ({token_hash}) - forcing JWT re-verification")
            del auth_cache[token_hash]

    logger.info(f"AUTH: Starting authentication - Token hash: {token_hash}, Token preview: {token[:20]}...")

    try:
        logger.debug(f"AUTH: Verifying token with Supabase - Token: {token[:20]}...")

        # Verify token - handle both Supabase tokens and custom JWT tokens
        try:
            # First try to decode as a custom JWT token.
            try:
                payload = jwt.decode(
                    token, 
                    settings.secret_key, 
                    algorithms=["HS256"],
                    audience="authenticated"  # Accept tokens with aud: "authenticated"
                )
                logger.info(f"AUTH: Successfully decoded custom JWT token for {payload.get('email')}")
                
                # Create a mock user object from JWT payload
                class MockUser:
                    def __init__(self, payload):
                        self.id = payload.get('id')
                        self.email = payload.get('email')
                        self.app_metadata = payload.get('app_metadata', {})
                        self.user_metadata = payload.get('user_metadata', {})
                        self.raw_app_metadata = payload.get('app_metadata', {})
                        self.tenant_id = self.app_metadata.get('tenant_id') or payload.get('tenant_id') or 'tenant-a'
                        
                user = MockUser(payload)
                
            except JWTError:
                # If custom JWT fails, try Supabase auth
                response = supabase.auth.get_user(token)
                user = response.user
                
        except Exception as e:
            # Malformed or invalid token (e.g., wrong number of segments)
            logger.warning(f"AUTH: Token verification failed (hash={token_hash}): {e.__class__.__name__}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing token",
            )

        logger.debug(
            f"AUTH: Supabase response - User ID: {user.id if user else None}, Email: {user.email if user else None}"
        )

        if not user:
            logger.warning("AUTH: No user found for provided token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )

        # Get user permissions.
        logger.debug(f"AUTH: Fetching permissions for user {user.id}")
        try:
            permissions_response = (
                supabase.service.table("user_permissions").select("section, action").eq("user_id", user.id).execute()
            )
            permissions = [Permission(**perm) for perm in permissions_response.data]
        except Exception as e:
            # Use empty permissions when permissions cannot be fetched.
            logger.info(f"AUTH: Using empty permissions for mock user {user.email}")
            permissions = []
        logger.debug(f"AUTH: Found {len(permissions)} permissions for user {user.id}")

        # Get user cities.
        logger.debug(f"AUTH: Fetching cities for user {user.id}")
        try:
            cities_response = supabase.service.table("users_city").select("city_name").eq("user_id", user.id).execute()
            logger.info(f"AUTH: Raw cities response for user {user.id}: {cities_response.data}")
            # Ensure cities are always lowercase for consistency
            user_cities = [city["city_name"].lower() for city in cities_response.data if city.get("city_name")]
        except Exception as e:
            # Use empty cities when city assignments cannot be fetched.
            logger.info(f"AUTH: Using empty cities for mock user {user.email}")
            user_cities = []
        logger.info(f"AUTH: Found cities for user {user.id} ({user.email}): {user_cities}")

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
            logger.info(f"AUTH: Using default tenant role for mock user {user.email}")
            tenant_role = getattr(user, 'app_metadata', {}).get('role', 'user')

        # Check if user is admin
        # Check both app_metadata and raw_app_metadata for the role
        role = None
        if hasattr(user, "raw_app_metadata") and user.raw_app_metadata:
            role = user.raw_app_metadata.get("role")
        elif hasattr(user, "app_metadata") and user.app_metadata:
            role = user.app_metadata.get("role")

        is_admin = user.email in ADMIN_EMAILS or role == "admin" or tenant_role == "admin"
        logger.info(
            "AUTH: Admin check for user %s - Email in admin list: %s, Role from metadata: %s, Tenant role: %s, Is admin: %s",
            user.email,
            user.email in ADMIN_EMAILS,
            role,
            tenant_role,
            is_admin,
        )

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
                logger.info(f"AUTH: Using default allowed cities for mock user {user.email}")
                allowed_city_map = {}

        # ✅ SIMPLIFIED: Let endpoint-specific logic handle admin vs user city differences
        # Auth only provides initial user city assignments for ALL users
        # Admin city logic is handled in individual endpoints (city_access_fast.py)
        logger.info(f"AUTH: User cities from users_city table: {user_cities}")
        logger.info(f"AUTH: Admin status: {is_admin} - city access will be determined by endpoint logic")

        # Use the comprehensive tenant resolver
        logger.info(f"==================== TENANT ID EXTRACTION ====================")
        logger.info(f"User: {user.email} (ID: {user.id})")

        # Use TenantResolver for comprehensive tenant resolution
        tenant_id = await TenantResolver.resolve_tenant_id(token=token, user_id=user.id, user_email=user.email)

        # If we found a tenant_id and it's not in the user's metadata, update it for next time
        current_tenant_in_metadata = None
        if hasattr(user, "raw_app_metadata") and user.raw_app_metadata:
            current_tenant_in_metadata = user.raw_app_metadata.get("tenant_id")
        elif hasattr(user, "app_metadata") and user.app_metadata:
            current_tenant_in_metadata = user.app_metadata.get("tenant_id")

        if tenant_id and current_tenant_in_metadata != tenant_id:
            logger.info(f"Updating user metadata with tenant_id for future requests...")
            asyncio.create_task(TenantResolver.update_user_tenant_metadata(user.id, tenant_id))

        logger.info(f"==================== TENANT ID EXTRACTION END ====================")

        auth_user = AuthenticatedUser(
            id=user.id,
            email=user.email,
            permissions=permissions,
            cities=user_cities,
            is_admin=is_admin,
            tenant_id=tenant_id,
        )

        # Cache the authentication result
        token_exp_claim = payload.get("exp") if 'payload' in locals() and isinstance(payload, dict) else None
        auth_cache[token_hash] = {
            "user": auth_user,
            "timestamp": datetime.now().timestamp(),
            "exp": token_exp_claim,
        }

        # Clean up old cache entries (keep cache size manageable)
        current_time = datetime.now().timestamp()
        expired_keys = [k for k, v in auth_cache.items() if current_time - v["timestamp"] > CACHE_DURATION]
        for key in expired_keys:
            del auth_cache[key]

        duration = (datetime.now() - start_time).total_seconds()
        logger.info(
            f"AUTH: OK - {user.email} (ID: {user.id}) in {duration:.2f}s, tenant={tenant_id}, cities={len(user_cities)}, perms={len(permissions)}"
        )

        return auth_user

    except Exception as error:
        duration = (datetime.now() - start_time).total_seconds()
        # If we raised HTTPException above, rethrow
        if isinstance(error, HTTPException):
            raise
        logger.warning(f"AUTH: Failed ({type(error).__name__}) in {duration:.2f}s: {str(error)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing token",
        )


def has_permission(user: AuthenticatedUser, section: str, action: str) -> bool:
    """Check if user has specific permission"""
    logger.info(f"Permission check for {user.email}: {section}.{action} - Is admin: {user.is_admin}")
    if user.is_admin:
        logger.info(f"User {user.email} is admin, granting permission")
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
        logger.info(f"User {user.email} has permission for {section}.{action}")
    else:
        # Log available permissions for debugging
        user_perms = [f"{p.section}.{p.action}" for p in user.permissions]
        logger.info(f"User {user.email} lacks permission for {section}.{action}. Available: {user_perms[:10]}")

    return has_perm


def require_permission(section: str, action: str):
    """Dependency to require specific permission"""

    def permission_checker(user: AuthenticatedUser = Depends(authenticate_request)):
        if not has_permission(user, section, action):
            logger.warning(
                f"Permission denied for user {user.email} - Required: {section}.{action}, Is admin: {user.is_admin}, User permissions: {[f'{p.section}.{p.action}' for p in user.permissions]}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions: {section}.{action}",
            )
        return user

    return permission_checker


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
            logger.warning(
                f"Permission denied for user {user.email} - Required any of: {permission_strings}, "
                f"Is admin: {user.is_admin}, User permissions: {[f'{p.section}.{p.action}' for p in user.permissions]}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions: requires any of {permission_strings}",
            )
        
        # Log which permission was matched for debugging
        matched_permissions = [
            f"{section}.{action}" for section, action in permissions
            if has_permission(user, section, action)
        ]
        logger.info(f"User {user.email} granted access via permissions: {matched_permissions}")
        
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
        logger.debug(f"WS_AUTH: Verifying WebSocket token - Token preview: {token[:20]}...")

        # Use same Supabase verification as regular authentication
        try:
            response = supabase.auth.get_user(token)
            user = response.user
        except Exception as e:
            logger.warning(f"WS_AUTH: Token verification failed: {e.__class__.__name__}")
            return None

        if not user:
            logger.warning("WS_AUTH: No user found for provided token")
            return None

        # Get user permissions (same as regular auth)
        logger.debug(f"WS_AUTH: Fetching permissions for user {user.id}")
        permissions_response = (
            supabase.service.table("user_permissions").select("section, action").eq("user_id", user.id).execute()
        )
        permissions = [Permission(**perm) for perm in permissions_response.data]

        # Get user cities (same table name as regular auth)
        logger.debug(f"WS_AUTH: Fetching cities for user {user.id}")
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
            logger.warning(f"WS_AUTH: Failed to fetch tenant role for user {user.id}: {tenant_role_error}")

        # Check if user is admin (same logic as regular auth)
        role = None
        if hasattr(user, "raw_app_metadata") and user.raw_app_metadata:
            role = user.raw_app_metadata.get("role")
        elif hasattr(user, "app_metadata") and user.app_metadata:
            role = user.app_metadata.get("role")

        is_admin = user.email in ADMIN_EMAILS or role == "admin" or tenant_role == "admin"

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
                logger.warning(f"WS_AUTH: Failed to resolve allowed cities for user {user.id}: {allowed_error}")

        # when no active properties exist in those cities. Users explicitly assigned
        # to cities in users_city table should keep that access regardless of properties.

        # Admin users get access to all cities from properties (same as regular auth)
        if is_admin:
            if allowed_city_map:
                user_cities = list(allowed_city_map.values())
                logger.debug(f"WS_AUTH: Admin user, granted access to all cities from properties: {user_cities}")
            else:
                # Keep user's explicitly assigned cities even if no properties exist
                logger.debug(f"WS_AUTH: Admin user, keeping assigned cities (no properties found): {user_cities}")
        
        logger.info(f"WS_AUTH: Final user cities after processing: {user_cities}")

        # Use the comprehensive tenant resolver (same as regular auth)
        logger.info(f"WS_AUTH: Resolving tenant for user {user.email}")
        tenant_id = await TenantResolver.resolve_tenant_id(token=token, user_id=user.id, user_email=user.email)

        auth_user = AuthenticatedUser(
            id=user.id,
            email=user.email,
            permissions=permissions,
            cities=user_cities,
            is_admin=is_admin,
            tenant_id=tenant_id,
        )

        logger.info(f"WS_AUTH: Success - {user.email} (ID: {user.id}), tenant={tenant_id}, cities={len(user_cities)}, perms={len(permissions)}")
        return auth_user

    except Exception as e:
        logger.error(f"WS_AUTH: Failed ({type(e).__name__}): {str(e)}")
        return None
