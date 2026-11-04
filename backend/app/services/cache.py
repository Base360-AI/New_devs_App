import json
import redis.asyncio as redis
from typing import Dict, Any, Optional
import os
import logging

logger = logging.getLogger(__name__)

# Initialize Redis client with fallback to environment
redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(redis_url)


async def get_revenue_summary(
    property_id: str, 
    tenant_id: str, 
    month: Optional[int] = None, 
    year: Optional[int] = None
) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    Cache key is strictly namespaced by tenant_id to prevent cross-tenant data leakage.
    """
    cache_key = f"revenue:{tenant_id}:{property_id}"
    if month and year:
        cache_key += f":{year}:{month}"

    # Try to get from cache
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        logger.debug(f"Redis cache lookup error for {cache_key}: {e}")

    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import calculate_total_revenue

    # Calculate revenue
    result = await calculate_total_revenue(property_id, tenant_id, month=month, year=year)

    # Cache the result for 5 minutes
    try:
        await redis_client.setex(cache_key, 300, json.dumps(result))
    except Exception as e:
        logger.debug(f"Redis cache store error for {cache_key}: {e}")

    return result
