import json
import redis.asyncio as redis
from typing import Dict, Any
import os

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


def _revenue_cache_key(tenant_id: str, property_id: str, month: int = None, year: int = None) -> str:
    """
    Builds the Redis key for a revenue summary.

    The tenant_id MUST be part of the key. Property IDs are only unique *within*
    a tenant (see database/schema.sql: properties has PRIMARY KEY (id, tenant_id)),
    so 'prop-001' refers to Beach House Alpha for tenant-a and to Mountain Lodge Beta
    for tenant-b. Keying on property_id alone lets whichever tenant queries first
    serve its revenue to the other one for the whole TTL.
    """
    scope = f"{year}-{month:02d}" if month and year else "all"
    return f"revenue:{tenant_id}:{property_id}:{scope}"


async def get_revenue_summary(
    property_id: str,
    tenant_id: str,
    month: int = None,
    year: int = None,
) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    """
    if not tenant_id:
        # Without a tenant we cannot isolate the cache, and we cannot scope the
        # query either. Fail loudly instead of serving someone else's data.
        raise ValueError("tenant_id is required to read a revenue summary")

    cache_key = _revenue_cache_key(tenant_id, property_id, month, year)

    # Try to get from cache
    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import calculate_total_revenue

    # Calculate revenue
    result = await calculate_total_revenue(property_id, tenant_id, month=month, year=year)

    # Cache the result for 5 minutes
    await redis_client.setex(cache_key, 300, json.dumps(result))

    return result


async def invalidate_revenue_cache(tenant_id: str, property_id: str) -> int:
    """Drops every cached revenue scope for one property of one tenant."""
    pattern = f"revenue:{tenant_id}:{property_id}:*"
    deleted = 0
    async for key in redis_client.scan_iter(match=pattern):
        await redis_client.delete(key)
        deleted += 1
    return deleted
