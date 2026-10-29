import json
import logging
import os
from typing import Any, Dict

import redis.asyncio as redis

from app.services.reservations import (
    DEFAULT_REPORT_MONTH,
    DEFAULT_REPORT_YEAR,
    calculate_monthly_revenue,
    revenue_cache_key,
)

logger = logging.getLogger(__name__)

redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


async def get_revenue_summary(
    property_id: str,
    tenant_id: str,
    year: int = DEFAULT_REPORT_YEAR,
    month: int = DEFAULT_REPORT_MONTH,
) -> Dict[str, Any] | None:
    cache_key = revenue_cache_key(tenant_id, property_id, year, month)

    try:
        cached = await redis_client.get(cache_key)
        if cached:
            logger.info("revenue cache hit key=%s", cache_key)
            return json.loads(cached)
    except Exception as exc:
        logger.warning("revenue cache read failed key=%s error=%s", cache_key, exc)

    result = await calculate_monthly_revenue(property_id, month, year, tenant_id)
    if result is None:
        return None

    try:
        await redis_client.setex(cache_key, 300, json.dumps(result))
    except Exception as exc:
        logger.warning("revenue cache write failed key=%s error=%s", cache_key, exc)

    return result