import json
import logging
import redis.asyncio as redis
from typing import Dict, Any
import os

logger = logging.getLogger(__name__)

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

async def get_revenue_summary(
    property_id: str,
    tenant_id: str,
    month: int = None,
    year: int = None,
) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    """
    # Property IDs are only unique within a tenant (prop-001 exists for two tenants), and
    # the period is part of the identity of the result, so both belong in the key.
    period_key = f"{year:04d}-{month:02d}" if month and year else "latest"
    cache_key = f"revenue:{tenant_id}:{property_id}:{period_key}"

    # Try to get from cache
    cached = await redis_client.get(cache_key)
    if cached:
        # An unreadable entry must degrade to a cache miss. Letting the decode error
        # escape would take the dashboard down over a disposable cache value.
        try:
            payload = json.loads(cached)
        except (ValueError, TypeError):
            logger.error("Discarding unreadable cache entry %s", cache_key)
            payload = None

        # Fail closed: never serve an entry stamped with another tenant, so a future
        # key-building mistake degrades to a cache miss instead of a data leak.
        if isinstance(payload, dict):
            if payload.get("tenant_id") == tenant_id:
                return payload
            logger.error(
                "Tenant mismatch on cache key %s: entry belongs to %s, request from %s",
                cache_key, payload.get("tenant_id"), tenant_id,
            )

    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import calculate_total_revenue

    # Calculate revenue
    result = await calculate_total_revenue(property_id, tenant_id, month, year)
    
    # Cache the result for 5 minutes
    await redis_client.setex(cache_key, 300, json.dumps(result))
    
    return result
