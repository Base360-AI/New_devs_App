import json
import redis.asyncio as redis
from typing import Dict, Any
import os

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

async def get_revenue_summary(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    """
    # New namespace also excludes entries produced by the old, shared cache.
    identity = [tenant_id, property_id]
    cache_key = "revenue:v2:" + json.dumps(identity, separators=(",", ":"))
    
    # Try to get from cache
    cached = await redis_client.get(cache_key)
    if cached:
        data = json.loads(cached)
        if isinstance(data, dict) and [data.get(k) for k in ("tenant_id", "property_id")] == identity:
            return data
    
    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import calculate_total_revenue
    
    # Calculate revenue
    result = await calculate_total_revenue(property_id, tenant_id)
    
    # Cache the result for 5 minutes
    await redis_client.setex(cache_key, 300, json.dumps(result))
    
    return result
