import json
import redis.asyncio as redis
from typing import Dict, Any
import os

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


def _revenue_cache_key(tenant_id: str, property_id: str) -> str:
    return f"revenue:{tenant_id}:{property_id}"


async def get_revenue_summary(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    """
    cache_key = _revenue_cache_key(tenant_id, property_id)

    try:
        cached = await redis_client.get(cache_key)
        if cached:
            payload = json.loads(cached)
            if payload.get("tenant_id") == tenant_id:
                return payload
    except Exception as e:
        print(f"Redis read error for {cache_key}: {e}")

    from app.services.reservations import calculate_total_revenue

    result = await calculate_total_revenue(property_id, tenant_id)

    try:
        await redis_client.setex(cache_key, 300, json.dumps(result))
    except Exception as e:
        print(f"Redis write error for {cache_key}: {e}")

    return result
