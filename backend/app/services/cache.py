import json
import os
import redis.asyncio as redis
from typing import Dict, Any

redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
REVENUE_CACHE_TTL_SECONDS = int(os.getenv("REVENUE_CACHE_TTL_SECONDS", "300"))


def revenue_cache_key(property_id: str, tenant_id: str) -> str:
    return f"revenue:{tenant_id}:{property_id}"


def cached_revenue_matches_tenant(cached_payload: Dict[str, Any], tenant_id: str) -> bool:
    return cached_payload.get("tenant_id") == tenant_id


async def get_revenue_summary(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing tenant-scoped caching.
    """
    cache_key = revenue_cache_key(property_id, tenant_id)

    cached = await redis_client.get(cache_key)
    if cached:
        payload = json.loads(cached)
        if cached_revenue_matches_tenant(payload, tenant_id):
            return payload

    from app.services.reservations import calculate_total_revenue

    result = await calculate_total_revenue(property_id, tenant_id)
    await redis_client.setex(cache_key, REVENUE_CACHE_TTL_SECONDS, json.dumps(result))
    return result
