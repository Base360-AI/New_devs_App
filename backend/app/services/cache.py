import json
import logging
import os

import redis.asyncio as redis
from redis.exceptions import RedisError
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

async def get_revenue_summary(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    """
    cache_key = f"revenue:{tenant_id}:{property_id}"
    
    # Redis is an optimization; a cache outage must not block authoritative
    # revenue reads from PostgreSQL.
    try:
        cached = await redis_client.get(cache_key)
    except RedisError:
        logger.warning("Revenue cache read failed for %s", cache_key, exc_info=True)
        cached = None

    if cached:
        return json.loads(cached)
    
    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import calculate_total_revenue
    
    # Calculate revenue
    result = await calculate_total_revenue(property_id, tenant_id)
    
    # A failed cache write must not discard a valid database result.
    try:
        await redis_client.setex(cache_key, 300, json.dumps(result))
    except RedisError:
        logger.warning("Revenue cache write failed for %s", cache_key, exc_info=True)
    
    return result
