import json
import redis.asyncio as redis
from typing import Dict, Any
import os

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

async def get_revenue_summary(
    property_id: str,
    tenant_id: str,
    month: int,
    year: int,
) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    """
    if not tenant_id:
        raise ValueError("tenant_id is required for revenue cache access")

    cache_key = (
        f"revenue:{tenant_id}:{property_id}:{year}:{month:02d}"
    )
    
    # Try to get from cache
    cached = await redis_client.get(cache_key)
    if cached:
        cached_result = json.loads(cached)
        if (
            cached_result.get("tenant_id") == tenant_id
            and cached_result.get("month") == month
            and cached_result.get("year") == year
        ):
            return cached_result
    
    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import calculate_monthly_revenue
    
    # Calculate revenue
    result = await calculate_monthly_revenue(
        property_id, tenant_id, month, year
    )
    
    # Cache the result for 5 minutes
    await redis_client.set(cache_key, json.dumps(result), ex=300)
    
    return result
