import json
import redis.asyncio as redis
from typing import Any, Dict, Optional
import os

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

async def get_revenue_summary(
    property_id: str, tenant_id: str, year: Optional[int] = None, month: Optional[int] = None
) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    """
    # Property IDs are only unique per tenant (prop-001 exists for several
    # clients), so the tenant must be part of the key, and so must the period.
    period = f"{year:04d}-{month:02d}" if year and month else "all"
    cache_key = f"revenue:{tenant_id}:{property_id}:{period}"

    # Try to get from cache
    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import calculate_total_revenue

    # Calculate revenue
    result = await calculate_total_revenue(property_id, tenant_id, year, month)

    # Cache the result for 5 minutes
    await redis_client.setex(cache_key, 300, json.dumps(result))

    return result
