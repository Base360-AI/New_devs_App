import json
import redis.asyncio as redis
from typing import Dict, Any
import os
import logging
from urllib.parse import quote
from redis.exceptions import RedisError

from app.services.reservations import calculate_monthly_revenue

logger = logging.getLogger(__name__)

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

def revenue_cache_key(property_id: str, tenant_id: str, month: int, year: int) -> str:
    # Versioning avoids reading legacy, tenant-independent entries.
    return f"revenue:v2:{quote(tenant_id, safe='')}:{quote(property_id, safe='')}:{year:04d}-{month:02d}"


async def get_revenue_summary(property_id: str, tenant_id: str, month: int, year: int) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    """
    cache_key = revenue_cache_key(property_id, tenant_id, month, year)
    
    # Try to get from cache
    try:
        cached = await redis_client.get(cache_key)
    except RedisError:
        logger.warning("Revenue cache unavailable; querying PostgreSQL")
        cached = None
    if cached:
        try:
            data = json.loads(cached)
            if isinstance(data, dict) and all(data.get(key) == value for key, value in {
                "tenant_id": tenant_id, "property_id": property_id, "month": month, "year": year
            }.items()):
                return data
        except (ValueError, TypeError):
            pass
    
    # Calculate revenue
    result = await calculate_monthly_revenue(property_id, tenant_id, month, year)
    
    # Cache the result for 5 minutes
    try:
        await redis_client.setex(cache_key, 300, json.dumps(result))
    except RedisError:
        logger.warning("Revenue cache write failed")
    
    return result
