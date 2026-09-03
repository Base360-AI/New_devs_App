"""
Ultra-fast city access API with aggressive caching
Designed for sub-50ms response times
Enhanced with centralized tenant context caching
"""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any, Optional
from ...core.auth import authenticate_request, require_admin
from ...core.tenant_access import require_user_in_operator_tenant
from ...models.auth import AuthenticatedUser
from ...database import supabase
from ...core.redis_client import redis_client
from ...core.tenant_cache import tenant_cache
import json
import time
import logging
import hashlib
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/fast", tags=["fast-access"])

# Cache configuration
CACHE_TTL = 3600  # 1 hour cache for city access
GLOBAL_CACHE_TTL = 7200  # 2 hours for global city list

def get_user_city_cache_key(user_id: str, tenant_id: str) -> str:
    """Generate cache key for user city access"""
    return f"city_access:v2:{tenant_id}:{user_id}"

def get_global_cities_cache_key(tenant_id: str) -> str:
    """Generate cache key for all available cities in tenant"""
    return f"global_cities:v2:{tenant_id}"

async def get_cached_city_access(user_id: str, tenant_id: str) -> Optional[List[str]]:
    """Get cached city access for user"""
    if not redis_client:
        return None
    
    try:
        cache_key = get_user_city_cache_key(user_id, tenant_id)
        cached = await redis_client.get(cache_key)
        if cached:
            logger.info(f"Cache HIT for user {user_id} city access")
            return json.loads(cached)
    except Exception as e:
        logger.warning(f"Redis error getting city cache: {e}")
    
    return None

async def set_cached_city_access(user_id: str, tenant_id: str, cities: List[str]) -> None:
    """Cache city access for user"""
    if not redis_client:
        return
    
    try:
        cache_key = get_user_city_cache_key(user_id, tenant_id)
        await redis_client.setex(
            cache_key,
            CACHE_TTL,
            json.dumps(cities)
        )
        logger.info(f"Cached city access for user {user_id}: {cities}")
    except Exception as e:
        logger.warning(f"Redis error setting city cache: {e}")

async def get_all_tenant_cities(tenant_id: str) -> List[str]:
    """Get all unique cities for a tenant with caching and robust fallback"""
    redis_healthy = False
    if redis_client:
        try:
            # Quick Redis health check with timeout
            await redis_client.ping()
            redis_healthy = True
            
            cache_key = get_global_cities_cache_key(tenant_id)
            cached = await redis_client.get(cache_key)
            if cached:
                logger.info(f"Cache HIT for tenant {tenant_id} global cities")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Redis unavailable or error getting global cities cache: {e}")
            redis_healthy = False
    
    # Fetch from database with timeout protection
    try:
        logger.info(f"🔍 TENANT_CITIES_DEBUG: Querying all_properties for tenant_id: {tenant_id}")
        
        result = supabase.service.table('all_properties')\
            .select('city')\
            .eq('tenant_id', tenant_id)\
            .not_.is_('city', 'null')\
            .limit(1000)\
            .execute()
        
        if hasattr(result, 'error') and result.error:
            logger.error(f"Database error fetching cities: {result.error}")
            # Return empty list instead of hardcoded fallback
            return []
        
        properties_count = len(result.data or [])
        logger.info(f"🏢 TENANT_CITIES_DEBUG: Found {properties_count} properties for tenant {tenant_id}")
        
        cities_set = set()
        for row in (result.data or []):
            if row.get('city'):
                city = row['city'].strip().lower()
                if city:
                    cities_set.add(city)
        
        cities = sorted(list(cities_set))
        logger.info(f"🌆 TENANT_CITIES_DEBUG: Extracted {len(cities)} unique cities: {cities}")
        
        # If no cities found, return empty list - don't use hardcoded fallback
        if not cities:
            logger.warning(f"⚠️ TENANT_CITIES_NO_DATA: No cities found for tenant {tenant_id} - this may indicate missing property data")
            # Clear any cached empty results for this tenant
            if redis_healthy:
                try:
                    cache_key = get_global_cities_cache_key(tenant_id)
                    await redis_client.delete(cache_key)
                    logger.info(f"🗑️ CACHE_CLEAR: Cleared empty cache for tenant {tenant_id}")
                except Exception as e:
                    logger.warning(f"Failed to clear cache for tenant {tenant_id}: {e}")
            # Return empty list instead of hardcoded cities
            cities = []
        
        # Cache the result only if Redis is healthy
        if redis_healthy:
            try:
                cache_key = get_global_cities_cache_key(tenant_id)
                await redis_client.setex(
                    cache_key,
                    GLOBAL_CACHE_TTL,
                    json.dumps(cities)
                )
            except Exception as e:
                logger.warning(f"Redis error setting global cities cache: {e}")
        
        return cities
    except Exception as e:
        logger.error(f"Error fetching tenant cities: {e}")
        return []

@router.get("/city-access")
async def get_city_access_fast(
    user: AuthenticatedUser = Depends(authenticate_request)
):
    """
    Ultra-fast endpoint to get user's accessible cities.
    Returns minimal data for maximum speed.
    """
    start_time = time.time()
    
    try:
        user_id = user.id
        tenant_id = user.tenant_id
        
        if not tenant_id or tenant_id.strip() == '':
            logger.error("TENANT_RESOLUTION_FAILED: Authenticated user has no valid tenant_id")
            return {
                "cities": [],
                "is_admin": False,
                "response_time_ms": int((time.time() - start_time) * 1000),
                "cache_hit": False,
                "error": "tenant_resolution_failed",
                "message": "Unable to determine tenant context for user"
            }
        
        # 🔒 VALIDATE: Ensure tenant_id is not suspicious
        if len(tenant_id) < 3 or tenant_id.isdigit():
            logger.error("SUSPICIOUS_TENANT_ID: Authenticated tenant identifier is invalid")
            return {
                "cities": [],
                "is_admin": False,
                "response_time_ms": int((time.time() - start_time) * 1000),
                "cache_hit": False,
                "error": "invalid_tenant_id",
                "message": "Invalid tenant identifier"
            }
        
        # Check if user is admin - enhanced to include tenant role check
        is_admin = user.is_admin
        
        # ✅ SIMPLIFIED ADMIN DETECTION: Use admin status from authentication
        # Additional tenant role check for completeness
        if not is_admin:
            try:
                tenant_role_result = supabase.service.table('user_tenants')\
                    .select('role, is_owner')\
                    .eq('user_id', user_id)\
                    .eq('tenant_id', tenant_id)\
                    .eq('is_active', True)\
                    .execute()
                
                if tenant_role_result.data and len(tenant_role_result.data) > 0:
                    tenant_role = tenant_role_result.data[0].get('role')
                    is_owner = tenant_role_result.data[0].get('is_owner', False)
                    is_admin = tenant_role in ['admin'] or is_owner
                    if is_admin:
                        logger.debug("ADMIN_DETECTED: Tenant administrator role found")
                
            except Exception as e:
                logger.warning("ADMIN_CHECK: Failed to check tenant role: %s", type(e).__name__)
        
        logger.debug("ADMIN_STATUS: is_admin=%s", is_admin)
        
        # ✅ SIMPLIFIED CACHING: Check cache for non-admin users only
        if not is_admin:
            cached_cities = await tenant_cache.get_city_access(tenant_id, user_id)
            if cached_cities is not None:
                elapsed = int((time.time() - start_time) * 1000)
                logger.debug("CACHE_HIT: %d cities", len(cached_cities))
                return {
                    "cities": cached_cities,
                    "is_admin": is_admin,
                    "response_time_ms": elapsed,
                    "cache_hit": True,
                    "tenant_id": tenant_id
                }
        else:
            logger.debug("ADMIN_CACHE_SKIP")
        
        # ✅ FETCH CITIES: Apply the corrected logic based on user type
        logger.debug("FETCHING_CITIES: admin=%s", is_admin)
        
        try:
            if is_admin:
                # ✅ SIMPLIFIED ADMIN LOGIC: Direct query of all_properties table filtered by tenant_id
                logger.debug("ADMIN_CITIES: Fetching tenant property cities")
                
                try:
                    # First check total properties in tenant (for debugging)
                    count_result = supabase.service.table('all_properties')\
                        .select('id', count='exact')\
                        .eq('tenant_id', tenant_id)\
                        .execute()
                    
                    total_properties = count_result.count if hasattr(count_result, 'count') else len(count_result.data or [])
                    logger.debug("ADMIN_CITIES: Total properties=%d", total_properties)
                    
                    # Now get cities
                    result = supabase.service.table('all_properties')\
                        .select('city')\
                        .eq('tenant_id', tenant_id)\
                        .not_.is_('city', 'null')\
                        .execute()
                    
                    logger.debug("ADMIN_CITIES: Query rows=%d", len(result.data or []))
                    
                    if result.error:
                        logger.error("ADMIN_CITIES_ERROR: Database query failed")
                        cities = []
                    else:
                        # Extract unique cities, filter out empty/null values
                        cities_set = set()
                        properties_count = len(result.data or [])
                        logger.debug("ADMIN_CITIES: Properties with city data=%d", properties_count)
                        
                        for row in (result.data or []):
                            city = row.get('city')
                            if city and isinstance(city, str):
                                city_clean = city.strip().lower()
                                if city_clean:
                                    cities_set.add(city_clean)
                        
                        cities = sorted(list(cities_set))
                        logger.debug("ADMIN_CITIES: Extracted %d unique cities", len(cities))
                        
                        if not cities:
                            logger.warning(
                                "ADMIN_CITIES_EMPTY: total_properties=%d, properties_with_city=%d",
                                total_properties,
                                properties_count,
                            )
                            
                except Exception as db_error:
                    logger.error("ADMIN_CITIES_DB_ERROR: %s", type(db_error).__name__)
                    cities = []
                
                logger.debug("ADMIN_ACCESS: %d cities", len(cities))
            else:
                # ✅ NON-ADMIN LOGIC: Query users_city table for assigned cities
                logger.debug("USER_CITIES: Querying city assignments")
                result = supabase.service.table('users_city')\
                    .select('city_name')\
                    .eq('user_id', user_id)\
                    .execute()
                
                if result.error:
                    logger.error("USER_CITIES_ERROR: Database query failed")
                    raise RuntimeError("Database query failed")
                
                # Extract and clean city names
                cities = []
                for row in (result.data or []):
                    city_name = row.get('city_name')
                    if city_name and isinstance(city_name, str):
                        city_clean = city_name.strip().lower()
                        if city_clean:
                            cities.append(city_clean)
                
                cities = sorted(list(set(cities)))  # Remove duplicates and sort
                logger.debug("USER_CITIES: %d assigned cities", len(cities))
            
            # 🔒 FINAL VALIDATION: Ensure we have valid results
            if not isinstance(cities, list):
                logger.error("INVALID_RESULT: Cities result is not a list")
                cities = []
            
            # Cache the result using centralized caching (will be handled automatically by tenant_cache.get_city_access)
            
            elapsed = int((time.time() - start_time) * 1000)
            logger.debug("CITY_ACCESS_SUCCESS: %d cities", len(cities))
            
            return {
                "cities": cities,
                "is_admin": is_admin,
                "response_time_ms": elapsed,
                "cache_hit": False,
                "tenant_id": tenant_id
            }
            
        except Exception as db_error:
            logger.error("DATABASE_FETCH_ERROR: %s", type(db_error).__name__)
            # Don't cache errors, return empty with error info
            elapsed = int((time.time() - start_time) * 1000)
            return {
                "cities": [],
                "is_admin": is_admin,
                "response_time_ms": elapsed,
                "cache_hit": False,
                "error": "database_fetch_failed",
                "message": "City access is temporarily unavailable"
            }
        
    except Exception as e:
        logger.error("Fast city access failed: %s", type(e).__name__)
        elapsed = int((time.time() - start_time) * 1000)
        return {
            "cities": [],
            "is_admin": False,
            "response_time_ms": elapsed,
            "cache_hit": False,
            "error": "city_access_failed"
        }

@router.post("/invalidate-city-cache")
async def invalidate_city_cache(
    user_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    user: AuthenticatedUser = Depends(authenticate_request)
):
    """
    Invalidate city access cache using centralized cache invalidation.
    Admin only endpoint for cache management.
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )

    if not user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active tenant membership",
        )

    if tenant_id and tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    tenant_id = tenant_id or user.tenant_id
    if user_id:
        await require_user_in_operator_tenant(user, user_id)
    
    if not redis_client.is_connected:
        return {"success": False, "message": "Redis not available"}
    
    try:
        keys_deleted = 0
        
        if user_id and not tenant_id:
            # Invalidate all caches for specific user
            keys_deleted = await tenant_cache.invalidate_user_cache(user_id)
        elif tenant_id and not user_id:
            # Invalidate all caches for specific tenant
            keys_deleted = await tenant_cache.invalidate_tenant_cache(tenant_id)
        elif user_id and tenant_id:
            # Invalidate specific user+tenant combination
            user_keys = await tenant_cache.invalidate_user_cache(user_id)
            tenant_keys = await tenant_cache.invalidate_tenant_cache(tenant_id)
            keys_deleted = user_keys + tenant_keys
        else:
            return {"success": False, "message": "Please specify user_id and/or tenant_id"}
        
        return {
            "success": True,
            "keys_deleted": keys_deleted,
            "message": f"Invalidated {keys_deleted} cache entries using centralized cache service"
        }
        
    except Exception as e:
        logger.error("City cache invalidation failed: %s", type(e).__name__)
        return {
            "success": False,
            "message": "Cache invalidation is temporarily unavailable"
        }

@router.get("/city-access-formatted")
async def get_city_access_formatted(
    user: AuthenticatedUser = Depends(authenticate_request)
):
    """
    Get formatted city access for dropdown components.
    Uses the fast endpoint internally and formats for UI.
    """
    # Get raw city access
    raw_result = await get_city_access_fast(user)
    
    cities = raw_result.get("cities", [])
    
    # Format for UI dropdowns
    formatted_cities = []
    
    # Add "All Cities" option
    formatted_cities.append({
        "value": "",
        "label": "All Cities"
    })
    
    # Add individual cities
    for city in cities:
        formatted_cities.append({
            "value": city,
            "label": city.title()
        })
    
    return {
        "cities": formatted_cities,
        "is_admin": raw_result.get("is_admin", False),
        "response_time_ms": raw_result.get("response_time_ms", 0),
        "cache_hit": raw_result.get("cache_hit", False),
        "total": len(cities)
    }

@router.post("/debug/clear-cache")
async def clear_city_cache_debug(
    user: AuthenticatedUser = Depends(require_admin)
):
    """Debug endpoint to clear city cache for current user's tenant"""
    try:
        tenant_id = user.tenant_id
        if not tenant_id:
            return {"success": False, "error": "No tenant_id found for user"}
        
        # Clear both caches
        cleared_count = 0
        
        # Clear global cities cache
        if redis_client:
            try:
                cache_key = get_global_cities_cache_key(tenant_id)
                result = await redis_client.delete(cache_key)
                if result:
                    cleared_count += 1
                logger.info("DEBUG_CACHE_CLEAR: Cleared global cities cache")
            except Exception as e:
                logger.error("Failed to clear global cache: %s", type(e).__name__)
        
        # Clear user-specific cache (if any)
        try:
            from ...core.tenant_cache import invalidate_city_access_cache
            invalidate_city_access_cache(user.id, tenant_id)
            cleared_count += 1
            logger.info("DEBUG_CACHE_CLEAR: Cleared user cache")
        except Exception as e:
            logger.error("Failed to clear user cache: %s", type(e).__name__)
        
        return {
            "success": True,
            "tenant_id": tenant_id,
            "caches_cleared": cleared_count,
            "message": f"Cleared {cleared_count} caches for tenant {tenant_id}"
        }
        
    except Exception as e:
        logger.error("Debug cache clear failed: %s", type(e).__name__)
        return {"success": False, "error": "cache_clear_failed"}
