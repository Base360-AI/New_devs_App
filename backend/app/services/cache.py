import json
import redis.asyncio as redis
from typing import Dict, Any
import os

redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


async def get_revenue_summary(
    property_id: str, tenant_id: str, month: int, year: int
) -> Dict[str, Any]:
    """
    Fetches monthly revenue summary, utilizing caching to improve performance.

    The cache key is scoped per tenant/property/month so different months
    don't collide and serve stale data from a neighbouring period.
    """
    cache_key = f"revenue:{tenant_id}:{property_id}:{year:04d}-{month:02d}"

    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    from app.services.reservations import calculate_monthly_revenue

    result = await calculate_monthly_revenue(property_id, tenant_id, month, year)

    # 5 minute TTL; short enough that new reservations show up quickly.
    await redis_client.setex(cache_key, 300, json.dumps(result))

    return result
