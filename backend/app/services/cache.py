import json
import logging
import redis.asyncio as redis
from typing import Any, Dict, Optional
import os

logger = logging.getLogger(__name__)

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

CACHE_TTL_SECONDS = 300


def _cache_key(property_id: str, tenant_id: str, month: Optional[int], year: Optional[int]) -> str:
    """Build a fully-qualified cache key.

    The tenant is part of the key because property IDs are only unique *within*
    a tenant (prop-001 exists for both Sunset and Ocean). Keying on property_id
    alone let whichever tenant missed the cache first serve its revenue to the
    other one. The period is in the key too, so a monthly total can never be
    served for an all-time request.
    """
    period = f"{year:04d}-{month:02d}" if month and year else "all-time"
    return f"revenue:{tenant_id}:{property_id}:{period}"


async def get_revenue_summary(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    """
    if not tenant_id:
        # Without a tenant we cannot scope either the query or the cache entry.
        raise ValueError("tenant_id is required to read a revenue summary")

    cache_key = _cache_key(property_id, tenant_id, month, year)

    # Try to get from cache
    try:
        cached = await redis_client.get(cache_key)
    except Exception as cache_error:
        # A cache outage must degrade to a live read, never to stale/foreign data.
        logger.warning(f"Revenue cache read failed for {cache_key}: {cache_error}")
        cached = None

    if cached:
        payload = json.loads(cached)
        # Defensive: refuse a cached entry that does not belong to this tenant.
        if payload.get("tenant_id") == tenant_id and payload.get("property_id") == property_id:
            return payload
        logger.error(f"Discarding mismatched cache entry for key {cache_key}")

    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import calculate_monthly_revenue, calculate_total_revenue

    # Calculate revenue
    if month and year:
        result = await calculate_monthly_revenue(property_id, tenant_id, month, year)
    else:
        result = await calculate_total_revenue(property_id, tenant_id)

    # Cache the result for 5 minutes
    try:
        await redis_client.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(result))
    except Exception as cache_error:
        logger.warning(f"Revenue cache write failed for {cache_key}: {cache_error}")

    return result


async def invalidate_revenue_cache(property_id: str, tenant_id: str) -> int:
    """Drop every cached revenue period for one property of one tenant."""
    deleted = 0
    try:
        async for key in redis_client.scan_iter(match=f"revenue:{tenant_id}:{property_id}:*"):
            deleted += await redis_client.delete(key)
    except Exception as cache_error:
        logger.warning(f"Revenue cache invalidation failed for {property_id}: {cache_error}")
    return deleted
