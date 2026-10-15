import json
import redis.asyncio as redis
from typing import Dict, Any, Optional
import os

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

async def get_revenue_summary(
    property_id: str, tenant_id: str, month: Optional[int] = None, year: Optional[int] = None
) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    """
    # Property IDs are only unique per tenant, so the key must include the tenant.
    cache_key = f"revenue:{tenant_id}:{property_id}"
    if month and year:
        cache_key += f":{year}-{month:02d}"
    
    # Try to get from cache
    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)
    
    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import calculate_monthly_revenue, calculate_total_revenue

    if month and year:
        result = await calculate_monthly_revenue(property_id, tenant_id, month, year)
    else:
        result = await calculate_total_revenue(property_id, tenant_id)
    
    # Cache the result for 5 minutes
    await redis_client.setex(cache_key, 300, json.dumps(result))
    
    return result
