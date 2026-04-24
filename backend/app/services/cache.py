import json
import redis.asyncio as redis
from typing import Dict, Any
import os

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

async def get_revenue_summary(property_id: str, tenant_id: str, month: int, year: int) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    Uses property caching key built strictly across tenant properties and date range.
    """
    
    # Safe cache key encapsulating all data-bound parameters to prevent collision
    cache_key = f"revenue:{tenant_id}:{property_id}:{year}:{month}"
    
    # Try to get from cache
    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)
    
    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import calculate_total_revenue
    
    # Calculate revenue passing explicit date bounds representing integer cents
    result = await calculate_total_revenue(property_id, tenant_id, month, year)
    
    # Cache the result for 5 minutes
    await redis_client.setex(cache_key, 300, json.dumps(result))
    
    return result

async def invalidate_revenue_cache(property_id: str, tenant_id: str, month: int = None, year: int = None):
    """
    Invalidates cached revenue summaries reliably. If month/year not provided,
    evicts all bounded cache entries per property+tenant.
    """
    if month and year:
        cache_key = f"revenue:{tenant_id}:{property_id}:{year}:{month}"
        await redis_client.delete(cache_key)
    else:
        # Invalidate all monthly data for this property securely
        pattern = f"revenue:{tenant_id}:{property_id}:*"
        keys = await redis_client.keys(pattern)
        if keys:
            await redis_client.delete(*keys)
