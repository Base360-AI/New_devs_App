import json
import os
from typing import Dict, Any

import redis.asyncio as redis

redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

CACHE_TTL_SECONDS = 300


async def get_revenue_summary(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """Return the revenue summary for a property, cached per tenant."""
    # Property IDs are only unique within a tenant (prop-001 exists for both
    # tenant-a and tenant-b), so the key has to include the tenant.
    cache_key = f"revenue:{tenant_id}:{property_id}"

    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    from app.services.reservations import calculate_total_revenue

    result = await calculate_total_revenue(property_id, tenant_id)
    await redis_client.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(result))
    return result
