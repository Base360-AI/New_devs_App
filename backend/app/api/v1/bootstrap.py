"""
Enterprise-level bootstrap endpoint for instant app initialization.
Returns all necessary tenant, permission, and module data in a single request.
Implements aggressive caching for near-instant response times.
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import logging
import time
import json
import hashlib
from ...core.auth import authenticate_request
from ...database import supabase
from ...models.auth import AuthenticatedUser
from pydantic import BaseModel
from cachetools import TTLCache, LRUCache
import asyncio

router = APIRouter()
logger = logging.getLogger(__name__)

# Enterprise-level caching with multiple layers
# L1 Cache: In-memory, per-user, short TTL for instant responses
l1_cache = TTLCache(maxsize=1000, ttl=60)  # 1 minute TTL, 1000 users max

# L2 Cache: In-memory, per-tenant, longer TTL for shared data
l2_cache = TTLCache(maxsize=100, ttl=300)  # 5 minutes TTL, 100 tenants max

# Response time targets
TARGET_RESPONSE_TIME_MS = 50  # Target 50ms response time
CACHE_WARM_UP_BATCH_SIZE = 10  # Number of users to warm up at once

class BootstrapResponse(BaseModel):
    """Complete bootstrap data for instant app initialization"""
    user: Dict[str, Any]
    tenant: Dict[str, Any]
    company_settings: Optional[Dict[str, Any]]
    permissions: List[Dict[str, str]]
    modules: List[str]
    smart_views: Dict[str, List[str]]
    subsections: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    cache_info: Dict[str, Any]

def get_cache_key(user_id: str, tenant_id: Optional[str]) -> str:
    """Generate cache key for user+tenant combination"""
    return f"bootstrap:{user_id}:{tenant_id or 'no-tenant'}"

def get_tenant_cache_key(tenant_id: str) -> str:
    """Generate cache key for tenant-level data"""
    return f"tenant:{tenant_id}"

async def get_user_permissions(user_id: str, email: str, role: Optional[str], tenant_id: Optional[str] = None) -> List[Dict[str, str]]:
    """Get user permissions including smart view permissions"""
    # Check if user is admin
    is_admin = role in ("admin", "owner")
    
    if is_admin:
        return [{"section": "*", "action": "*"}]
    
    # Fetch permissions from database - using user_permissions table like auth.py does
    try:
        # Get direct user permissions (same as auth.py)
        perms_result = (
            supabase
            .table('user_permissions')
            .select('section, action')
            .eq('user_id', user_id)
            .execute()
        )
        
        permissions = perms_result.data or []
        
        logger.info(f"[get_user_permissions] Raw DB result for user {user_id}: {len(permissions)} permissions")
        if permissions:
            logger.info(f"[get_user_permissions] Sample permissions from DB: {permissions[:5]}")
        
        # Also check for smart view permissions
        # If user has access to any smart view section, add individual smart view permissions
        if tenant_id:
            # Get all smart views for the tenant
            smart_views_result = (
                supabase
                .table('reservation_subsections')
                .select('id, name')
                .eq('tenant_id', tenant_id)
                .eq('is_active', True)
                .execute()
            )
            
            smart_views = smart_views_result.data or []
            
            # Check if user should have smart view access
            # 1. Check if user already has any smart view permissions
            has_smart_view_access = any(p['section'].startswith('smart_view_') for p in permissions)
            # 2. Check if user has general permissions that would grant smart view access
            has_cs_access = any(p['section'] == 'customer_service' and p['action'] == 'read' for p in permissions)
            has_reservations_access = any(p['section'] == 'reservations' and p['action'] == 'read' for p in permissions)
            has_reservation_tool_access = any(p['section'] == 'reservation_tool' and p['action'] == 'read' for p in permissions)
            
            # If user has any of these permissions, they should have access to smart views
            if has_smart_view_access or has_cs_access or has_reservations_access or has_reservation_tool_access:
                for view in smart_views:
                    permissions.append({
                        "section": f"smart_view_{view['id']}",
                        "action": "read"
                    })
                logger.info(f"Added {len(smart_views)} smart view permissions for user {user_id}")
        
        logger.info(f"Fetched {len(permissions)} total permissions for user {user_id}")
        return permissions
    except Exception as e:
        logger.error(f"Error fetching permissions for user {user_id}: {e}")
        return []

async def get_tenant_data(tenant_id: str) -> Dict[str, Any]:
    """Get tenant data with L2 caching"""
    # Check L2 cache first
    cache_key = get_tenant_cache_key(tenant_id)
    if cache_key in l2_cache:
        logger.debug(f"L2 cache hit for tenant {tenant_id}")
        return l2_cache[cache_key]
    
    tenant_data = {}
    
    # Fetch tenant info
    try:
        tenant_result = (
            supabase
            .table('tenants')
            .select('*')
            .eq('id', tenant_id)
            .maybe_single()
            .execute()
        )
        tenant_data['info'] = tenant_result.data or {}
    except Exception as e:
        logger.error(f"Error fetching tenant info: {e}")
        tenant_data['info'] = {}
    
    # Fetch company settings
    try:
        settings_result = (
            supabase
            .table('company_settings')
            .select('*')
            .eq('tenant_id', tenant_id)
            .maybe_single()
            .execute()
        )
        
        if settings_result.data:
            tenant_data['company_settings'] = settings_result.data
        else:
            # Don't provide defaults - let frontend show skeleton loader
            tenant_data['company_settings'] = None
    except Exception as e:
        logger.error(f"Error fetching company settings: {e}")
        # Don't provide defaults - let frontend show skeleton loader
        tenant_data['company_settings'] = None
    
    # Fetch enabled modules
    try:
        modules_result = (
            supabase
            .table('org_modules')
            .select('module')
            .eq('tenant_id', tenant_id)
            .eq('status', 'enabled')
            .execute()
        )
        tenant_data['modules'] = [m['module'] for m in (modules_result.data or [])]
        logger.info(f"Fetched {len(tenant_data['modules'])} modules for tenant {tenant_id}: {tenant_data['modules']}")
    except Exception as e:
        logger.error(f"Error fetching modules: {e}")
        tenant_data['modules'] = []
    
    # Cache the tenant data
    l2_cache[cache_key] = tenant_data
    return tenant_data

async def get_user_smart_views(user_id: str) -> Dict[str, List[str]]:
    """Get user's accessible smart views grouped by section based on their permissions"""
    try:
        # Get user's permissions to find smart view permissions
        permissions_result = (
            supabase
            .table('user_permissions')
            .select('section')
            .eq('user_id', user_id)
            .execute()
        )
        
        # Extract smart view IDs from permissions
        smart_view_ids = []
        if permissions_result.data:
            for perm in permissions_result.data:
                section = perm.get('section', '')
                if section.startswith('smart_view_'):
                    # Extract the UUID from smart_view_UUID format
                    view_id = section.replace('smart_view_', '')
                    if view_id:
                        smart_view_ids.append(view_id)
        
        logger.info(f"Found {len(smart_view_ids)} smart view permissions for user {user_id}")
        if smart_view_ids:
            logger.info(f"Smart view IDs from permissions: {smart_view_ids[:10]}")  # Log first 10
        
        # If no smart views, return empty
        if not smart_view_ids:
            return {}
        
        # Get the smart view details for these IDs
        smart_views_result = (
            supabase
            .table('reservation_subsections')
            .select('id, name, section, sections, is_active')
            .in_('id', smart_view_ids)
            .eq('is_active', True)
            .execute()
        )
        
        # Log what we found in the database
        if smart_views_result.data:
            logger.info(f"Found {len(smart_views_result.data)} smart views in database for user's permissions")
            for sv in smart_views_result.data[:5]:  # Log first 5
                logger.info(f"  Smart view: {sv.get('name')} (ID: {sv.get('id')}, sections: {sv.get('sections')}, section: {sv.get('section')})")
        
        # Group smart views by section
        smart_views_by_section: Dict[str, List[str]] = {}
        if smart_views_result.data:
            for smart_view in smart_views_result.data:
                view_id = smart_view.get('id')
                
                # Get sections - use 'sections' array first, fall back to 'section'
                sections = smart_view.get('sections', [])
                if not sections and smart_view.get('section'):
                    sections = [smart_view.get('section')]
                
                logger.debug(f"Processing smart view: id={view_id}, sections={sections}, name={smart_view.get('name')}")
                
                # Add to each section this smart view belongs to
                for section in sections:
                    if section:
                        # Handle legacy section names
                        if section == 'daily_cs_task':
                            section = 'customer_service'
                        
                        if section not in smart_views_by_section:
                            smart_views_by_section[section] = []
                        
                        if view_id not in smart_views_by_section[section]:
                            smart_views_by_section[section].append(view_id)
        
        logger.info(f"User {user_id} smart views by section: {smart_views_by_section}")
        return smart_views_by_section
    except Exception as e:
        logger.error(f"Error fetching user smart views: {e}")
        logger.error(f"Full error details: {str(e)}", exc_info=True)
        return {}

async def get_reservation_subsections(tenant_id: str) -> List[Dict[str, Any]]:
    """Get reservation subsections for the tenant"""
    try:
        result = (
            supabase
            .table('reservation_subsections')
            .select('*')
            .eq('tenant_id', tenant_id)
            .order('order_index')
            .execute()
        )
        # Filter for enabled subsections if the column exists
        data = result.data or []
        # Check if is_enabled column exists and filter
        if data and 'is_enabled' in data[0]:
            data = [item for item in data if item.get('is_enabled', True)]
        return data
    except Exception as e:
        logger.error(f"Error fetching reservation subsections: {e}")
        return []

async def get_user_departments(user_id: str) -> List[Dict[str, Any]]:
    """Get user's department assignments with department details."""
    try:
        # Step 1: Get the department IDs for the user
        user_dept_result = (
            supabase.service.table("user_departments")
            .select("department_id")
            .eq("user_id", user_id)
            .execute()
        )
        if not user_dept_result.data:
            return []

        department_ids = [item['department_id'] for item in user_dept_result.data]
        if not department_ids:
            return []

        # Step 2: Get the details for those departments
        departments_result = (
            supabase.service.table("departments")
            .select("*")
            .in_("id", department_ids)
            .execute()
        )
        
        return departments_result.data or []
    except Exception as e:
        logger.error(f"Error fetching user departments for user {user_id}: {e}")
        return []

@router.get("/bootstrap", response_model=BootstrapResponse)
async def bootstrap_app(
    current_user: AuthenticatedUser = Depends(authenticate_request),
    force_refresh: bool = False
):
    """
    Enterprise bootstrap endpoint - returns all necessary data for instant app initialization.
    
    Features:
    - Multi-layer caching (L1 per-user, L2 per-tenant)
    - Parallel data fetching
    - Sub-50ms response time target
    - Automatic cache warming
    - Force refresh option for cache bypass
    """
    start_time = time.time()
    
    # Get tenant_id
    tenant_id = current_user.tenant_id
    if not tenant_id:
        # Try to get from user_tenants
        try:
            tenant_result = (
                supabase
                .table('user_tenants')
                .select('tenant_id')
                .eq('user_id', current_user.id)
                .eq('is_active', True)
                .maybe_single()
                .execute()
            )
            if tenant_result.data:
                tenant_id = tenant_result.data.get('tenant_id')
        except Exception as e:
            logger.error(f"Error getting tenant_id: {e}")
    
    # Check L1 cache first (unless force refresh)
    cache_key = get_cache_key(current_user.id, tenant_id)
    cache_hit = False
    
    if not force_refresh and cache_key in l1_cache:
        logger.debug("L1 bootstrap cache hit")
        cache_hit = True
        cached_data = l1_cache[cache_key]
        
        # Add cache metadata
        cached_data['cache_info'] = {
            'cache_hit': True,
            'cache_level': 'L1',
            'response_time_ms': int((time.time() - start_time) * 1000),
            'cache_age_seconds': int(time.time() - cached_data.get('cached_at', 0))
        }
        
        return BootstrapResponse(**cached_data)
    
    # Parallel fetch all data
    logger.debug("[BOOTSTRAP] Fetching data; admin=%s", current_user.is_admin)
    
    # Create tasks for parallel execution
    tasks = []
    
    # Task 1: Get user permissions (including smart view permissions)
    tasks.append(get_user_permissions(
        current_user.id,
        current_user.email or "",
        'admin' if current_user.is_admin else None,
        tenant_id
    ))
    
    # Task 2: Get tenant data (if we have tenant_id)
    if tenant_id:
        tasks.append(get_tenant_data(tenant_id))
    else:
        # Create a simple async function that returns default data
        async def default_tenant_data():
            return {
                'info': {},
                'company_settings': {
                    "company_name": "The Flex",
                    "logo_url": None,
                    "domain": None,
                    "header_color": "#284E4C",
                    "primary_color": "#FFF9E9",
                    "secondary_color": "#FFFDF6",
                    "accent_color": "#284E4C",
                    "favicon_url": None,
                    "tenant_id": None
                },
                'modules': []
            }
        tasks.append(default_tenant_data())
    
    # Task 3: Get smart views
    tasks.append(get_user_smart_views(current_user.id))
    
    # Task 4: Get reservation subsections (if we have tenant_id)
    if tenant_id:
        tasks.append(get_reservation_subsections(tenant_id))
    else:
        # Create a simple async function that returns empty list
        async def default_subsections():
            return []
        tasks.append(default_subsections())
    
    # Task 5: Get user departments
    tasks.append(get_user_departments(current_user.id))

    # Execute all tasks in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Handle results with detailed logging
    permissions = results[0] if not isinstance(results[0], Exception) else []
    tenant_data = results[1] if not isinstance(results[1], Exception) else {}
    smart_views = results[2] if not isinstance(results[2], Exception) else {}
    subsections = results[3] if not isinstance(results[3], Exception) else []
    departments = results[4] if not isinstance(results[4], Exception) else []
    
    # Log detailed permission information
    logger.debug("[BOOTSTRAP] Permission count=%d", len(permissions))
    if permissions:
        # Log first 10 permissions for debugging
        logger.info(f"[BOOTSTRAP] Sample permissions: {permissions[:10]}")
        # Log specifically for reservations-related permissions
        reservations_perms = [p for p in permissions if 'reservations' in str(p.get('section', '')).lower() or 'reservation' in str(p.get('section', '')).lower()]
        if reservations_perms:
            logger.info(f"[BOOTSTRAP] Reservation permissions found: {reservations_perms}")
        else:
            logger.info("[BOOTSTRAP] No reservation-related permissions found")
    else:
        logger.warning("[BOOTSTRAP] No permissions found for authenticated user")
    
    # Build response
    response_data = {
        'user': {
            'id': current_user.id,
            'email': current_user.email,
            'role': 'admin' if current_user.is_admin else 'user',
            'is_admin': current_user.is_admin,
            'departments': departments
        },
        'tenant': tenant_data.get('info', {}),
        'company_settings': tenant_data.get('company_settings', {}),
        'permissions': permissions,
        'modules': tenant_data.get('modules', []),
        'smart_views': smart_views,
        'subsections': subsections,
        'metadata': {
            'tenant_id': tenant_id,
            'timestamp': datetime.utcnow().isoformat(),
            'version': '1.0.0'
        },
        'cache_info': {
            'cache_hit': cache_hit,
            'cache_level': 'none',
            'response_time_ms': int((time.time() - start_time) * 1000),
            'cache_age_seconds': 0
        },
        'cached_at': time.time()
    }
    
    # Cache the response
    l1_cache[cache_key] = response_data
    
    # Log performance metrics
    response_time_ms = int((time.time() - start_time) * 1000)
    if response_time_ms > TARGET_RESPONSE_TIME_MS:
        logger.warning(f"Bootstrap response time {response_time_ms}ms exceeds target {TARGET_RESPONSE_TIME_MS}ms")
    else:
        logger.info(f"Bootstrap response time {response_time_ms}ms - within target")
    
    # Remove cached_at from response
    del response_data['cached_at']
    
    return BootstrapResponse(**response_data)

@router.post("/bootstrap/invalidate-cache")
async def invalidate_cache(
    current_user: AuthenticatedUser = Depends(authenticate_request),
    scope: str = "user"  # "user", "tenant", or "all"
):
    """
    Invalidate bootstrap cache.
    
    Args:
        scope: Cache invalidation scope
            - "user": Invalidate only current user's cache
            - "tenant": Invalidate all caches for user's tenant
            - "all": Invalidate all caches (admin only)
    """
    tenant_id = current_user.tenant_id
    
    if scope == "user":
        # Invalidate user's L1 cache
        cache_key = get_cache_key(current_user.id, tenant_id)
        if cache_key in l1_cache:
            del l1_cache[cache_key]
        logger.info("Invalidated bootstrap cache for authenticated user")
        
    elif scope == "tenant" and tenant_id:
        # Invalidate tenant's L2 cache
        tenant_cache_key = get_tenant_cache_key(tenant_id)
        if tenant_cache_key in l2_cache:
            del l2_cache[tenant_cache_key]
        
        # Also invalidate all L1 caches for this tenant
        keys_to_remove = [k for k in l1_cache.keys() if f":{tenant_id}" in k]
        for key in keys_to_remove:
            del l1_cache[key]
        
        logger.info(f"Invalidated cache for tenant {tenant_id}")
        
    elif scope == "all":
        # Admin only - clear all caches
        is_admin = current_user.is_admin
        
        if not is_admin:
            raise HTTPException(status_code=403, detail="Admin access required")
        
        l1_cache.clear()
        l2_cache.clear()
        logger.info("Invalidated all caches")
    
    return {"success": True, "scope": scope}

@router.get("/bootstrap/cache-stats")
async def get_cache_stats(
    current_user: AuthenticatedUser = Depends(authenticate_request)
):
    """Get cache statistics for monitoring"""
    is_admin = current_user.is_admin
    
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    return {
        "l1_cache": {
            "size": len(l1_cache),
            "max_size": l1_cache.maxsize,
            "ttl_seconds": l1_cache.ttl,
            "utilization": f"{(len(l1_cache) / l1_cache.maxsize * 100):.1f}%"
        },
        "l2_cache": {
            "size": len(l2_cache),
            "max_size": l2_cache.maxsize,
            "ttl_seconds": l2_cache.ttl,
            "utilization": f"{(len(l2_cache) / l2_cache.maxsize * 100):.1f}%"
        },
        "target_response_time_ms": TARGET_RESPONSE_TIME_MS
    }
