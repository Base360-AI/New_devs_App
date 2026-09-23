import json
import logging
import os
from typing import Any, Dict

import redis.asyncio as redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


async def get_revenue_summary(
    property_id: str, tenant_id: str, month: int = 3, year: int = 2024
) -> Dict[str, Any]:
    # Versioning excludes stale results produced by previous calculations.
    cache_key = "revenue:v2:" + json.dumps([tenant_id, property_id, year, month])
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except (RedisError, ValueError):
        logger.warning("Revenue cache unavailable; querying database")

    from app.services.reservations import calculate_total_revenue
    result = await calculate_total_revenue(property_id, tenant_id, month, year)
    try:
        await redis_client.setex(cache_key, 300, json.dumps(result))
    except RedisError:
        logger.warning("Could not cache revenue summary")
    return result
