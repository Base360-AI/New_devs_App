import json
import logging
import os
from typing import Any, Dict

import redis.asyncio as redis

logger = logging.getLogger(__name__)

redis_client = redis.Redis.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379/0")
)


async def get_revenue_summary(
    property_id: str,
    tenant_id: str,
    year: int,
    month: int,
) -> Dict[str, Any]:
    """Fetch a tenant-, property-, and month-scoped revenue summary."""
    cache_key = f"revenue:{tenant_id}:{property_id}:{year}:{month}"

    try:
        cached = await redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except (redis.RedisError, json.JSONDecodeError, TypeError):
        logger.warning("Revenue cache read failed for key %s", cache_key, exc_info=True)

    from app.services.reservations import calculate_total_revenue

    result = await calculate_total_revenue(property_id, tenant_id, year, month)

    try:
        await redis_client.setex(cache_key, 300, json.dumps(result))
    except redis.RedisError:
        logger.warning("Revenue cache write failed for key %s", cache_key, exc_info=True)

    return result
