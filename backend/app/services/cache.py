import json
import logging
import redis.asyncio as redis
from typing import Dict, Any
from app.config import settings

logger = logging.getLogger(__name__)

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(settings.redis_url)


def build_revenue_cache_key(property_id: str, tenant_id: str, month: int, year: int) -> str:
    return f"revenue:{tenant_id}:{property_id}:{year}:{month:02d}"


async def get_revenue_summary(property_id: str, tenant_id: str, month: int, year: int) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    """
    cache_key = build_revenue_cache_key(property_id, tenant_id, month, year)
    
    # Try to get from cache
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            payload = json.loads(cached)
            if payload.get("tenant_id") == tenant_id:
                return payload
            logger.warning("Ignoring tenant-mismatched cached revenue payload for %s", cache_key)
    except Exception as exc:
        logger.warning("Revenue cache read failed for %s: %s", cache_key, exc)
    
    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import calculate_monthly_revenue
    
    # Calculate revenue
    result = await calculate_monthly_revenue(property_id, tenant_id, month, year)
    
    # Cache the result for 5 minutes
    try:
        await redis_client.setex(cache_key, 300, json.dumps(result))
    except Exception as exc:
        logger.warning("Revenue cache write failed for %s: %s", cache_key, exc)
    
    return result
