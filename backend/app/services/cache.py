import json
import logging
import os
from typing import Any

import redis.asyncio as redis

from app.services.reservations import calculate_monthly_revenue, get_tenant_property
from app.services.revenue_reporting import revenue_cache_key

logger = logging.getLogger(__name__)

# Redis is an optimization only; revenue always remains available from Postgres
# when a cache operation fails.
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


async def get_revenue_summary(
    property_id: str,
    tenant_id: str,
    *,
    year: int,
    month: int,
) -> dict[str, Any]:
    """Fetch an authorized, property-local monthly revenue summary.

    The ownership check deliberately happens before the cache lookup.  That makes
    a cached value inaccessible to a tenant that does not own the property.
    """
    property_record = await get_tenant_property(property_id, tenant_id)
    cache_key = revenue_cache_key(tenant_id, property_id, year, month)

    try:
        cached = await redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as error:  # Cache availability must not break reporting.
        logger.warning("Revenue cache read failed: %s", error)

    result = await calculate_monthly_revenue(
        property_id,
        tenant_id,
        month,
        year,
        property_timezone=property_record["timezone"],
    )
    result["property_name"] = property_record["name"]
    result["timezone"] = property_record["timezone"]

    try:
        await redis_client.setex(cache_key, 300, json.dumps(result))
    except Exception as error:  # Cache availability must not break reporting.
        logger.warning("Revenue cache write failed: %s", error)

    return result
