import json
import logging
from typing import Any, Dict, Optional

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)
redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=0.5)


async def get_revenue_summary(
    property_id: str, tenant_id: str, month: Optional[str] = None
) -> Dict[str, Any]:
    # Scope every cached result to the authenticated tenant as well as property/month.
    cache_key = f"revenue:v2:{tenant_id}:{property_id}:{month or 'latest'}"
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as exc:
        logger.warning("Revenue cache read failed; using database: %s", type(exc).__name__)

    from app.services.reservations import calculate_total_revenue

    result = await calculate_total_revenue(property_id, tenant_id, month)
    if result.get("not_found"):
        return result
    try:
        await redis_client.setex(cache_key, 300, json.dumps(result))
    except Exception as exc:
        logger.warning("Revenue cache write failed: %s", type(exc).__name__)
    return result
