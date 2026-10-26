import json
import redis.asyncio as redis
from typing import Dict, Any
import os

from app.services.reservations import REPORT_MONTH, REPORT_YEAR

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


def _revenue_cache_key(tenant_id: str, property_id: str, year: int, month: int) -> str:
    return f"revenue:{tenant_id}:{property_id}:{year}-{month:02d}"


async def get_revenue_summary(
    property_id: str,
    tenant_id: str,
    year: int = REPORT_YEAR,
    month: int = REPORT_MONTH,
) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    """
    cache_key = _revenue_cache_key(tenant_id, property_id, year, month)

    cached = await redis_client.get(cache_key)
    if cached:
        payload = json.loads(cached)
        if payload.get("tenant_id") == tenant_id:
            return payload

    from app.services.reservations import calculate_total_revenue

    result = await calculate_total_revenue(property_id, tenant_id, year=year, month=month)
    if result.get("tenant_id") != tenant_id:
        result = {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": "0.00",
            "currency": "USD",
            "count": 0,
        }

    await redis_client.setex(cache_key, 300, json.dumps(result))
    return result
