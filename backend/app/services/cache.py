import json
import redis.asyncio as redis
from typing import Dict, Any
import os

from ..core.redis_client import redis_client

async def get_revenue_summary(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    """
    cache_key = f"revenue:{property_id}:{tenant_id}"
    
    # Try to get from cache
    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)
    
    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import calculate_total_revenue
    
    # Calculate revenue
    result = await calculate_total_revenue(property_id, tenant_id)
    
    # Cache the result for 5 minutes (default for this redis_client helper class)
    await redis_client.set(cache_key, json.dumps(result))
    
    return result
