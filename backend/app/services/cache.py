import json
import logging
import os
from typing import Any, Dict, Optional

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.services.reservations import calculate_revenue

logger = logging.getLogger(__name__)
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


def _cache_key(
    property_id: str, tenant_id: str, year: int, month: Optional[int]
) -> str:
    period = f"{year}-{month:02d}" if month is not None else f"{year}-annual"
    return f"revenue:v2:{tenant_id}:{property_id}:{period}"


async def get_revenue_summary(
    property_id: str,
    tenant_id: str,
    year: int,
    month: Optional[int] = None,
) -> Dict[str, Any]:
    cache_key = _cache_key(property_id, tenant_id, year, month)
    try:
        cached = await redis_client.get(cache_key)
    except RedisError as error:
        logger.warning(f"Revenue cache read failed: {error}")
        cached = None

    if cached:
        try:
            result = json.loads(cached)
            if (
                result.get("tenant_id") == tenant_id
                and result.get("property_id") == property_id
                and result.get("year") == year
                and result.get("month") == month
            ):
                return result
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass

        try:
            await redis_client.delete(cache_key)
        except RedisError as error:
            logger.warning(f"Revenue cache cleanup failed: {error}")

    result = await calculate_revenue(property_id, tenant_id, year, month)
    try:
        await redis_client.setex(cache_key, 300, json.dumps(result))
    except RedisError as error:
        logger.warning(f"Revenue cache write failed: {error}")

    return result


async def invalidate_revenue_summary(tenant_id: str, property_id: str) -> None:
    pattern = f"revenue:v2:{tenant_id}:{property_id}:*"
    try:
        keys = [key async for key in redis_client.scan_iter(match=pattern)]
        if keys:
            await redis_client.delete(*keys)
    except RedisError as error:
        logger.warning(f"Revenue cache invalidation failed: {error}")
