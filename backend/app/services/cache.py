import json
import redis.asyncio as redis
from typing import Dict, Any
import os

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

async def get_revenue_summary(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.

    SECURITY: The cache key MUST be scoped by tenant_id. Multiple tenants can own
    properties that share the same property_id (e.g. both Sunset Properties and
    Ocean Rentals have a "prop-001"), so a key based only on property_id would
    cause one tenant's revenue numbers to be served to another tenant.
    """
    if not tenant_id:
        # Refuse to use an unscoped cache key - protects against cross-tenant leaks.
        raise ValueError("tenant_id is required to build a tenant-scoped cache key")

    cache_key = f"revenue:{tenant_id}:{property_id}"

    cached = await redis_client.get(cache_key)
    if cached:
        cached_data = json.loads(cached)
        # Defensive check: if a stale entry from before the fix leaks through,
        # ignore it when the tenant_id does not match the requesting tenant.
        if cached_data.get("tenant_id") == tenant_id:
            return cached_data

    from app.services.reservations import calculate_total_revenue

    result = await calculate_total_revenue(property_id, tenant_id)

    # Cache the result for 5 minutes
    await redis_client.setex(cache_key, 300, json.dumps(result))

    return result
