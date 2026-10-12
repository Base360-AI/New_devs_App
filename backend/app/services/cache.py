import json
import logging
import redis.asyncio as redis
from typing import Dict, Any, Optional
import os

logger = logging.getLogger(__name__)

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

CACHE_TTL_SECONDS = 300


def build_cache_key(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> str:
    """
    Builds the revenue cache key.

    The tenant is part of the key because property ids are only unique within a
    tenant: properties.id is PRIMARY KEY (id, tenant_id), so two tenants can
    both own a 'prop-001'. Keying on property_id alone lets one tenant's totals
    be served to another.

    The period is part of the key so a month's figure is never served as the
    all-time total.
    """
    key = f"revenue:{tenant_id}:{property_id}"
    if month is not None and year is not None:
        key = f"{key}:{year}-{month:02d}"
    return key


async def get_revenue_summary(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.

    Supplying month and year scopes the figure to that calendar month in the
    property's own timezone; otherwise the all-time total is returned.
    """
    cache_key = build_cache_key(property_id, tenant_id, month, year)

    # Try to get from cache
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        # A cache outage must not take the dashboard down; fall through and
        # calculate from the database instead.
        logger.warning(f"Cache read failed for {cache_key}: {e}")

    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import (
        calculate_monthly_revenue,
        calculate_total_revenue,
    )

    # Calculate revenue
    if month is not None and year is not None:
        result = await calculate_monthly_revenue(property_id, tenant_id, month, year)
    else:
        result = await calculate_total_revenue(property_id, tenant_id)

    # Cache the result for 5 minutes
    try:
        await redis_client.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(result))
    except Exception as e:
        logger.warning(f"Cache write failed for {cache_key}: {e}")

    return result
