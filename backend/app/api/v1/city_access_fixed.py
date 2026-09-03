"""
Fixed city access API with proper tenant isolation
Addresses security vulnerabilities in the original city access system
"""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Dict, Any, Optional
from ...core.auth import authenticate_request
from ...models.auth import AuthenticatedUser
from ...database import supabase
from ...core.redis_client import redis_client
import json
import time
import logging
import hashlib
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/city-access-fixed", tags=["city-access-fixed"])

# Cache configuration
CACHE_TTL = 3600  # 1 hour cache for city access
GLOBAL_CACHE_TTL = 7200  # 2 hours for global city list

def get_user_city_cache_key(user_id: str, tenant_id: str) -> str:
    """Generate cache key for user city access"""
    return f"city_access:v3:{tenant_id}:{user_id}"

def get_global_cities_cache_key(tenant_id: str) -> str:
    """Generate cache key for all available cities in tenant"""
    return f"global_cities:v3:{tenant_id}"

async def get_cached_city_access(user_id: str, tenant_id: str) -> Optional[List[str]]:
    """Get cached city access for user"""
    if not redis_client:
        return None
    
    try:
        cache_key = get_user_city_cache_key(user_id, tenant_id)
        cached = await redis_client.get(cache_key)
        if cached:
            logger.info(f"Cache HIT for user {user_id} city access in tenant {tenant_id}")
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
        logger.info(f"Cached city access for user {user_id} in tenant {tenant_id}: {cities}")
    except Exception as e:
        logger.warning(f"Redis error setting city cache: {e}")

async def get_all_tenant_cities(tenant_id: str) -> List[str]:
    """Get all unique cities for a tenant with caching - FIXED with tenant isolation"""
    # Try cache first
    if redis_client:
        try:
            cache_key = get_global_cities_cache_key(tenant_id)
            cached = await redis_client.get(cache_key)
            if cached:
                logger.info(f"Cache HIT for tenant {tenant_id} global cities")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Redis error getting global cities cache: {e}")
    
    # Fetch from database with proper tenant isolation
    try:
        result = supabase.service.table('all_properties')\
            .select('city')\
            .eq('tenant_id', tenant_id)\
            .not_.is_('city', 'null')\
            .neq('city', '')\
            .execute()
        
        cities_set = set()
        for row in (result.data or []):
            if row.get('city'):
                city = row['city'].strip().lower()
                if city:
                    cities_set.add(city)
        
        cities = sorted(list(cities_set))
        logger.info(f"Tenant {tenant_id} has {len(cities)} cities: {cities}")
        
        # Cache the result
        if redis_client:
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

@router.get("/user-cities")
async def get_user_city_access_fixed(
    user: AuthenticatedUser = Depends(authenticate_request)
):
    """
    FIXED: Get user's accessible cities with proper tenant isolation.
    Addresses security vulnerabilities in the original system.
    """
    start_time = time.time()
    
    try:
        user_id = user.id
        tenant_id = user.tenant_id
        
        if not tenant_id or tenant_id.strip() == '':
            logger.error("SECURITY: Authenticated user has no tenant context")
            return {
                "cities": [],
                "is_admin": False,
                "response_time_ms": int((time.time() - start_time) * 1000),
                "error": "no_tenant_context",
                "message": "User must have valid tenant context"
            }
        
        # Check if user is admin
        is_admin = user.is_admin
        
        # Try cache first with tenant isolation
        cached_cities = await get_cached_city_access(user_id, tenant_id)
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
        
        # Fetch from database with proper tenant isolation
        logger.debug("CACHE_MISS: Fetching city access")
        
        try:
            if is_admin:
                # Admin gets all cities in their tenant
                cities = await get_all_tenant_cities(tenant_id)
                logger.debug("ADMIN_ACCESS: %d cities", len(cities))
            else:
                # FIXED: Regular user gets cities with tenant isolation
                result = supabase.service.table('users_city')\
                    .select('city_name')\
                    .eq('user_id', user_id)\
                    .eq('tenant_id', tenant_id)\
                    .execute()
                
                if result.error:
                    logger.error("DATABASE_ERROR: Failed to fetch user cities")
                    raise Exception(f"Database error: {result.error}")
                
                user_cities = [row['city_name'].lower().strip() for row in (result.data or []) if row.get('city_name')]
                logger.debug("USER_CITIES: %d assigned cities", len(user_cities))
                
                # Additional validation: ensure cities exist in tenant
                if user_cities:
                    all_tenant_cities = await get_all_tenant_cities(tenant_id)
                    cities = sorted(list(set(user_cities).intersection(set(all_tenant_cities))))
                    
                    if len(cities) != len(user_cities):
                        invalid_cities = set(user_cities) - set(all_tenant_cities)
                        logger.warning("INVALID_CITIES: %d assignments are outside tenant", len(invalid_cities))
                else:
                    cities = []
                    logger.warning("NO_CITIES: Authenticated user has no city assignments")
            
            # Validate results
            if not isinstance(cities, list):
                logger.error("INVALID_RESULT: Cities result is not a list")
                cities = []
            
            # Cache the result with tenant isolation
            await set_cached_city_access(user_id, tenant_id, cities)
            
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
            elapsed = int((time.time() - start_time) * 1000)
            return {
                "cities": [],
                "is_admin": is_admin,
                "response_time_ms": elapsed,
                "cache_hit": False,
                "error": "database_fetch_failed",
                "message": f"Failed to fetch cities: {str(db_error)}"
            }
        
    except Exception as e:
        logger.error(f"Error in fixed city access: {e}")
        elapsed = int((time.time() - start_time) * 1000)
        return {
            "cities": [],
            "is_admin": False,
            "response_time_ms": elapsed,
            "cache_hit": False,
            "error": str(e)
        }

@router.post("/assign-city")
async def assign_city_to_user_fixed(
    user_id: str,
    city_name: str,
    user: AuthenticatedUser = Depends(authenticate_request)
):
    """
    FIXED: Assign city access to user with proper tenant isolation.
    Only admins can assign cities, and only within their own tenant.
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    try:
        # Get the tenant context
        tenant_id = user.tenant_id
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Admin must have valid tenant context"
            )
        
        # Validate that the target user belongs to the same tenant
        target_user_check = supabase.service.table('user_tenants')\
            .select('tenant_id')\
            .eq('user_id', user_id)\
            .eq('tenant_id', tenant_id)\
            .eq('is_active', True)\
            .execute()
        
        if not target_user_check.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found in your tenant"
            )
        
        # Use the helper function to add city access with validation
        try:
            result = supabase.rpc('add_user_city_access', {
                'p_user_id': user_id,
                'p_tenant_id': tenant_id,
                'p_city_name': city_name
            }).execute()
            
            # Invalidate cache for the user
            if redis_client:
                try:
                    cache_key = get_user_city_cache_key(user_id, tenant_id)
                    await redis_client.delete(cache_key)
                except Exception as e:
                    logger.warning(f"Failed to invalidate cache: {e}")
            
            return {
                "success": True,
                "message": f"City access granted: {city_name}",
                "user_id": user_id,
                "city_name": city_name.lower(),
                "tenant_id": tenant_id
            }
            
        except Exception as e:
            if "does not exist in tenant" in str(e):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"City '{city_name}' does not exist in your tenant"
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="City access assignment is temporarily unavailable"
                )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error assigning city access: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="City access assignment is temporarily unavailable"
        )

@router.delete("/remove-city")
async def remove_city_from_user_fixed(
    user_id: str,
    city_name: str,
    user: AuthenticatedUser = Depends(authenticate_request)
):
    """
    FIXED: Remove city access from user with proper tenant isolation.
    Only admins can remove cities, and only within their own tenant.
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    try:
        tenant_id = user.tenant_id
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Admin must have valid tenant context"
            )
        
        # Remove city access with tenant validation
        result = supabase.service.table('users_city')\
            .delete()\
            .eq('user_id', user_id)\
            .eq('city_name', city_name.lower())\
            .eq('tenant_id', tenant_id)\
            .execute()
        
        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="City access not found for this user in your tenant"
            )
        
        # Invalidate cache for the user
        if redis_client:
            try:
                cache_key = get_user_city_cache_key(user_id, tenant_id)
                await redis_client.delete(cache_key)
            except Exception as e:
                logger.warning(f"Failed to invalidate cache: {e}")
        
        return {
            "success": True,
            "message": f"City access removed: {city_name}",
            "user_id": user_id,
            "city_name": city_name.lower(),
            "tenant_id": tenant_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing city access: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="City access removal is temporarily unavailable"
        )

@router.get("/tenant-cities")
async def get_tenant_cities_fixed(
    user: AuthenticatedUser = Depends(authenticate_request)
):
    """
    FIXED: Get all cities available in the user's tenant.
    Provides proper tenant isolation.
    """
    try:
        tenant_id = user.tenant_id
        if not tenant_id:
            return {
                "cities": [],
                "total": 0,
                "error": "no_tenant_context"
            }
        
        cities = await get_all_tenant_cities(tenant_id)
        
        # Format for UI
        formatted_cities = []
        for city in cities:
            formatted_cities.append({
                "id": city,
                "name": city.title(),
                "value": city
            })
        
        return {
            "cities": formatted_cities,
            "total": len(cities),
            "tenant_id": tenant_id
        }
        
    except Exception as e:
        logger.error(f"Error fetching tenant cities: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="City lookup is temporarily unavailable"
        )

@router.get("/debug")
async def debug_city_access(
    user: AuthenticatedUser = Depends(authenticate_request)
):
    """
    Debug endpoint to help troubleshoot city access issues.
    Admin only.
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    try:
        tenant_id = user.tenant_id
        user_id = user.id
        
        # Get user's city assignments
        user_cities_result = supabase.service.table('users_city')\
            .select('city_name, tenant_id')\
            .eq('user_id', user_id)\
            .execute()
        
        # Get all tenant cities
        tenant_cities = await get_all_tenant_cities(tenant_id) if tenant_id else []
        
        # Get user tenant info
        user_tenant_result = supabase.service.table('user_tenants')\
            .select('tenant_id, role, is_active')\
            .eq('user_id', user_id)\
            .execute()
        
        return {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "is_admin": user.is_admin,
            "user_city_assignments": user_cities_result.data or [],
            "tenant_cities": tenant_cities,
            "user_tenant_relationships": user_tenant_result.data or [],
            "cache_keys": {
                "user_cities": get_user_city_cache_key(user_id, tenant_id) if tenant_id else "no_tenant",
                "global_cities": get_global_cities_cache_key(tenant_id) if tenant_id else "no_tenant"
            }
        }
        
    except Exception as e:
        logger.error("City access diagnostics failed: %s", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Diagnostics are temporarily unavailable"
        )
