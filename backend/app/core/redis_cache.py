"""
Redis Cache Service for Guest Portal
Provides server-side caching for improved performance across all users
"""
import json
import logging
import hashlib
from typing import Optional, Any, Dict, List, Union
from datetime import datetime, timedelta
import redis
import asyncio
from functools import wraps

logger = logging.getLogger(__name__)

class RedisCacheService:
    """Redis caching service for guest portal data"""
    
    def __init__(self, redis_url: str = "redis://localhost:6379", default_ttl: int = 300):
        """
        Initialize Redis cache service
        
        Args:
            redis_url: Redis connection URL
            default_ttl: Default TTL in seconds (5 minutes)
        """
        try:
            self.redis_client = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=1)
            self.default_ttl = default_ttl
            
            # Test connection with timeout
            self.redis_client.ping()
            logger.info("Redis cache service initialized successfully")
        except Exception as e:
            logger.warning(f"Redis not available, caching disabled: {e}")
            self.redis_client = None
    
    def _make_key(self, prefix: str, identifier: str, tenant_id: Optional[str] = None, **kwargs) -> str:
        """
        Create cache key with tenant isolation
        
        Args:
            prefix: Cache key prefix (e.g., 'templates', 'portals')
            identifier: Unique identifier
            tenant_id: Tenant ID for isolation
            **kwargs: Additional parameters to include in key
        """
        key_parts = [prefix, identifier]
        
        # Add tenant isolation
        if tenant_id:
            key_parts.append(f"tenant:{tenant_id}")
        
        # Add additional parameters
        for key, value in sorted(kwargs.items()):
            if value is not None:
                key_parts.append(f"{key}:{value}")
        
        return ":".join(key_parts)
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if not self.redis_client:
            return None
        
        try:
            value = await asyncio.get_event_loop().run_in_executor(
                None, self.redis_client.get, key
            )
            
            if value:
                logger.info(f"[REDIS CACHE HIT] {key}")
                cache_metrics.record_hit()
                return json.loads(value)
            else:
                logger.info(f"[REDIS CACHE MISS] {key}")
                cache_metrics.record_miss()
                return None
                
        except Exception as e:
            logger.error(f"Error getting from cache {key}: {e}")
            cache_metrics.record_error()
            return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with TTL"""
        if not self.redis_client:
            return False
        
        try:
            ttl = ttl or self.default_ttl
            await asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: self.redis_client.setex(key, ttl, json.dumps(value, default=str))
            )
            
            logger.info(f"[REDIS CACHE SET] {key} (TTL: {ttl}s)")
            return True
            
        except Exception as e:
            logger.error(f"Error setting cache {key}: {e}")
            cache_metrics.record_error()
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if not self.redis_client:
            return False
        
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, self.redis_client.delete, key
            )
            
            logger.debug(f"Cache DELETE: {key}")
            return bool(result)
            
        except Exception as e:
            logger.error(f"Error deleting cache {key}: {e}")
            return False
    
    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern"""
        if not self.redis_client:
            return 0
        
        try:
            keys = await asyncio.get_event_loop().run_in_executor(
                None, self.redis_client.keys, pattern
            )
            
            if keys:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, self.redis_client.delete, *keys
                )
                logger.debug(f"Cache DELETE PATTERN: {pattern} ({len(keys)} keys)")
                return result
            
            return 0
            
        except Exception as e:
            logger.error(f"Error deleting cache pattern {pattern}: {e}")
            return 0
    
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        if not self.redis_client:
            return False
        
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, self.redis_client.exists, key
            )
            return bool(result)
            
        except Exception as e:
            logger.error(f"Error checking cache existence {key}: {e}")
            return False

class GuestPortalCache:
    """Guest Portal specific caching operations"""
    
    def __init__(self, cache_service: RedisCacheService):
        self.cache = cache_service
        
        # Cache TTLs (in seconds)
        self.TTL_TEMPLATES = 30 * 60  # 30 minutes
        self.TTL_PORTALS_SUMMARY = 5 * 60  # 5 minutes (more dynamic)
        self.TTL_VERIFICATION_COUNTS = 15 * 60  # 15 minutes
        self.TTL_PORTAL_DATA = 10 * 60  # 10 minutes
        self.TTL_ORDERS = 3 * 60  # 3 minutes (most dynamic)
        self.TTL_PRECHECKIN_FLOW = 8 * 60  # 8 minutes (optimized for sharing while maintaining freshness)
    
    # Templates caching
    async def get_templates(self, tenant_id: str) -> Optional[List[Dict]]:
        """Get cached templates list for tenant"""
        key = self.cache._make_key("templates", "all", tenant_id=tenant_id)
        return await self.cache.get(key)

    async def set_templates(self, tenant_id: str, templates: List[Dict]) -> bool:
        """Cache templates list for tenant"""
        key = self.cache._make_key("templates", "all", tenant_id=tenant_id)
        return await self.cache.set(key, templates, self.TTL_TEMPLATES)

    async def get_template_with_assignments(self, template_id: str, tenant_id: str) -> Optional[Dict]:
        """
        Get cached individual template with full assignment data
        Use for template detail views to avoid repeated fetches
        """
        key = self.cache._make_key("template_full", template_id, tenant_id=tenant_id)
        return await self.cache.get(key)

    async def set_template_with_assignments(self, template_id: str, tenant_id: str, template_data: Dict) -> bool:
        """
        Cache individual template with assignments (properties, upsells, guides)
        TTL: 1 hour (template details change less frequently than portal counts)
        """
        key = self.cache._make_key("template_full", template_id, tenant_id=tenant_id)
        # Use longer TTL for detailed template data (60 minutes)
        return await self.cache.set(key, template_data, 60 * 60)

    async def invalidate_template_full(self, template_id: str, tenant_id: str) -> bool:
        """Invalidate individual template cache"""
        key = self.cache._make_key("template_full", template_id, tenant_id=tenant_id)
        return await self.cache.delete(key)

    async def invalidate_templates(self, tenant_id: str) -> bool:
        """Invalidate all templates cache for tenant (list + individual templates)"""
        # Invalidate list cache
        list_pattern = self.cache._make_key("templates", "*", tenant_id=tenant_id)
        await self.cache.delete_pattern(list_pattern)

        # Invalidate individual template caches
        full_pattern = self.cache._make_key("template_full", "*", tenant_id=tenant_id)
        await self.cache.delete_pattern(full_pattern)

        # Also invalidate template configurations when templates change
        config_pattern = self.cache._make_key("template_config", "*", tenant_id=tenant_id)
        await self.cache.delete_pattern(config_pattern)

        logger.info(f"[CACHE INVALIDATE] All templates cache for tenant {tenant_id}")
        return True
    
    # Verification counts caching
    async def get_verification_counts(self, tenant_id: str) -> Optional[Dict]:
        """Get cached verification counts for tenant"""
        key = self.cache._make_key("verification_counts", "all", tenant_id=tenant_id)
        return await self.cache.get(key)
    
    async def set_verification_counts(self, tenant_id: str, counts: Dict) -> bool:
        """Cache verification counts for tenant"""
        key = self.cache._make_key("verification_counts", "all", tenant_id=tenant_id)
        return await self.cache.set(key, counts, self.TTL_VERIFICATION_COUNTS)
    
    # Template portals caching
    async def get_template_portals(self, template_id: str, tenant_id: str, page: int = 1, search: Optional[str] = None) -> Optional[Dict]:
        """Get cached portals summary for template"""
        key = self.cache._make_key(
            "template_portals", template_id, 
            tenant_id=tenant_id, page=page, search=search or "none"
        )
        return await self.cache.get(key)
    
    async def set_template_portals(self, template_id: str, tenant_id: str, data: Dict, page: int = 1, search: Optional[str] = None) -> bool:
        """Cache portals summary for template"""
        key = self.cache._make_key(
            "template_portals", template_id, 
            tenant_id=tenant_id, page=page, search=search or "none"
        )
        return await self.cache.set(key, data, self.TTL_PORTALS_SUMMARY)
    
    async def invalidate_template_portals(self, template_id: str, tenant_id: str) -> bool:
        """Invalidate all cached portals for a template"""
        pattern = self.cache._make_key("template_portals", template_id, tenant_id=tenant_id) + "*"
        await self.cache.delete_pattern(pattern)
        return True
    
    # Portal data caching
    async def get_portal_data(self, portal_token: str, tenant_id: str) -> Optional[Dict]:
        """Get cached portal data"""
        key = self.cache._make_key("portal_data", portal_token, tenant_id=tenant_id)
        return await self.cache.get(key)
    
    async def set_portal_data(self, portal_token: str, tenant_id: str, data: Dict) -> bool:
        """Cache portal data"""
        key = self.cache._make_key("portal_data", portal_token, tenant_id=tenant_id)
        return await self.cache.set(key, data, self.TTL_PORTAL_DATA)
    
    # Orders caching
    async def get_orders(self, portal_token: str, tenant_id: str) -> Optional[Dict]:
        """Get cached orders for portal"""
        key = self.cache._make_key("orders", portal_token, tenant_id=tenant_id)
        return await self.cache.get(key)
    
    async def set_orders(self, portal_token: str, tenant_id: str, orders: Dict) -> bool:
        """Cache orders for portal"""
        key = self.cache._make_key("orders", portal_token, tenant_id=tenant_id)
        return await self.cache.set(key, orders, self.TTL_ORDERS)
    
    # Pre-checkin flow caching
    async def get_precheckin_flow(self, portal_token: str, tenant_id: str) -> Optional[Dict]:
        """Get cached pre-checkin flow data for portal"""
        key = self.cache._make_key("precheckin_flow", portal_token, tenant_id=tenant_id)
        result = await self.cache.get(key)
        if result:
            logger.info(f"[PRECHECKIN CACHE HIT] Portal {portal_token[:8]}... (tenant: {tenant_id})")
        else:
            logger.info(f"[PRECHECKIN CACHE MISS] Portal {portal_token[:8]}... (tenant: {tenant_id})")
        return result
    
    async def set_precheckin_flow(self, portal_token: str, tenant_id: str, flow_data: Dict) -> bool:
        """Cache pre-checkin flow data for portal"""
        key = self.cache._make_key("precheckin_flow", portal_token, tenant_id=tenant_id)
        success = await self.cache.set(key, flow_data, self.TTL_PRECHECKIN_FLOW)
        if success:
            logger.info(f"[PRECHECKIN CACHE SET] Portal {portal_token[:8]}... (tenant: {tenant_id}, TTL: {self.TTL_PRECHECKIN_FLOW}s)")
        return success
    
    async def invalidate_precheckin_flow(self, portal_token: str, tenant_id: str) -> bool:
        """Invalidate pre-checkin flow cache for portal"""
        key = self.cache._make_key("precheckin_flow", portal_token, tenant_id=tenant_id)
        success = await self.cache.delete(key)
        if success:
            logger.info(f"[PRECHECKIN CACHE INVALIDATE] Portal {portal_token[:8]}... (tenant: {tenant_id})")
        return success
    
    # Template-level caching for sharing across users
    async def get_template_config(self, template_id: str, tenant_id: str) -> Optional[Dict]:
        """Get cached template configuration data that can be shared across users"""
        key = self.cache._make_key("template_config", template_id, tenant_id=tenant_id)
        return await self.cache.get(key)
    
    async def set_template_config(self, template_id: str, tenant_id: str, config_data: Dict) -> bool:
        """Cache template configuration data for sharing across users"""
        key = self.cache._make_key("template_config", template_id, tenant_id=tenant_id)
        # Use longer TTL since template configs change less frequently
        return await self.cache.set(key, config_data, self.TTL_TEMPLATES)
    
    async def invalidate_template_config(self, template_id: str, tenant_id: str) -> bool:
        """Invalidate template configuration cache"""
        key = self.cache._make_key("template_config", template_id, tenant_id=tenant_id)
        return await self.cache.delete(key)
    
    # Bulk invalidation methods
    async def invalidate_tenant_cache(self, tenant_id: str) -> int:
        """Invalidate all cache for a tenant"""
        pattern = f"*:tenant:{tenant_id}*"
        return await self.cache.delete_pattern(pattern)
    
    async def invalidate_portal_cache(self, portal_token: str, tenant_id: str) -> bool:
        """Invalidate all cache for a specific portal"""
        patterns = [
            self.cache._make_key("portal_data", portal_token, tenant_id=tenant_id),
            self.cache._make_key("orders", portal_token, tenant_id=tenant_id),
            self.cache._make_key("precheckin_flow", portal_token, tenant_id=tenant_id)
        ]
        
        for pattern in patterns:
            await self.cache.delete(pattern)
        
        return True

def cache_response(
    cache_key_func,
    ttl: int = 300,
    cache_instance: Optional[GuestPortalCache] = None
):
    """
    Decorator for caching API responses in Redis
    
    Args:
        cache_key_func: Function that takes (*args, **kwargs) and returns cache key
        ttl: Time to live in seconds
        cache_instance: GuestPortalCache instance (will use default if None)
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if not cache_instance:
                return await func(*args, **kwargs)
            
            try:
                # Generate cache key
                cache_key = cache_key_func(*args, **kwargs)
                
                # Try to get from cache first
                cached_result = await cache_instance.cache.get(cache_key)
                if cached_result:
                    logger.info(f"Cache HIT: {cache_key}")
                    return cached_result
                
                # Cache miss - execute function
                logger.info(f"Cache MISS: {cache_key}")
                result = await func(*args, **kwargs)
                
                # Cache the result
                await cache_instance.cache.set(cache_key, result, ttl)
                
                return result
                
            except Exception as e:
                logger.error(f"Cache error in {func.__name__}: {e}")
                # Return direct function result if caching fails
                return await func(*args, **kwargs)
        
        return wrapper
    return decorator

# Global cache instance
_redis_cache_service = None
_guest_portal_cache = None

def get_redis_cache() -> Optional[RedisCacheService]:
    """Get the global Redis cache service instance"""
    global _redis_cache_service
    
    if _redis_cache_service is None:
        try:
            # Try to initialize Redis cache
            from ..config import settings
            redis_url = getattr(settings, 'REDIS_URL', 'redis://localhost:6379')
            _redis_cache_service = RedisCacheService(redis_url)
        except Exception as e:
            logger.warning(f"Redis cache not available: {e}")
            _redis_cache_service = None
    
    return _redis_cache_service

def get_guest_portal_cache() -> Optional[GuestPortalCache]:
    """Get the global guest portal cache instance"""
    global _guest_portal_cache
    
    if _guest_portal_cache is None:
        redis_service = get_redis_cache()
        if redis_service:
            _guest_portal_cache = GuestPortalCache(redis_service)
    
    return _guest_portal_cache

# Cache key generators for decorators
def make_templates_cache_key(tenant_id: str) -> str:
    """Generate cache key for templates list"""
    return f"templates:all:tenant:{tenant_id}"

def make_verification_counts_cache_key(tenant_id: str) -> str:
    """Generate cache key for verification counts"""
    return f"verification_counts:all:tenant:{tenant_id}"

def make_template_portals_cache_key(template_id: str, tenant_id: str, page: int = 1, search: Optional[str] = None) -> str:
    """Generate cache key for template portals summary"""
    search_key = hashlib.sha256((search or "").encode()).hexdigest()[:12] if search else "none"
    return f"template_portals:{template_id}:tenant:{tenant_id}:page:{page}:search:{search_key}"

def make_portal_data_cache_key(portal_token: str, tenant_id: str) -> str:
    """Generate cache key for portal data"""
    return f"portal_data:{portal_token}:tenant:{tenant_id}"

def make_orders_cache_key(portal_token: str, tenant_id: str) -> str:
    """Generate cache key for portal orders"""
    return f"orders:{portal_token}:tenant:{tenant_id}"

def make_precheckin_flow_cache_key(portal_token: str, tenant_id: str) -> str:
    """Generate cache key for pre-checkin flow data"""
    return f"precheckin_flow:{portal_token}:tenant:{tenant_id}"

def make_template_config_cache_key(template_id: str, tenant_id: str) -> str:
    """Generate cache key for template configuration data"""
    return f"template_config:{template_id}:tenant:{tenant_id}"

# Performance monitoring
class CacheMetrics:
    """Track cache performance metrics"""
    
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.errors = 0
        self.start_time = datetime.now()
    
    def record_hit(self):
        self.hits += 1
    
    def record_miss(self):
        self.misses += 1
    
    def record_error(self):
        self.errors += 1
    
    def get_stats(self) -> Dict:
        total_requests = self.hits + self.misses
        hit_rate = (self.hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "hits": self.hits,
            "misses": self.misses,
            "errors": self.errors,
            "hit_rate_percent": round(hit_rate, 2),
            "total_requests": total_requests,
            "uptime_minutes": (datetime.now() - self.start_time).total_seconds() / 60
        }

# Global metrics instance
cache_metrics = CacheMetrics()
