import json
import logging
from typing import Dict, Any
from app.core.redis_client import redis_client
from app.services.reservations import calculate_monthly_revenue

logger = logging.getLogger(__name__)


def get_revenue_cache_key(tenant_id: str, property_id: str, year: int, month: int) -> str:
    """Generate tenant- and period-isolated cache key."""
    return f"revenue:{tenant_id}:{property_id}:{year}:{month}"


async def get_revenue_summary(
    property_id: str,
    tenant_id: str,
    year: int = 2024,
    month: int = 3,
    custom_redis=None
) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    Cache keys are isolated by tenant, property, and period.
    """
    cache_key = get_revenue_cache_key(tenant_id, property_id, year, month)
    client = custom_redis or redis_client

    # 1. Attempt cache lookup
    try:
        if client is not None and hasattr(client, "get"):
            cached = await client.get(cache_key)
            if cached:
                cached_data = None
                if isinstance(cached, (str, bytes)):
                    cached_data = json.loads(cached)
                elif isinstance(cached, dict):
                    cached_data = cached

                if isinstance(cached_data, dict):
                    if (
                        cached_data.get("tenant_id") == tenant_id
                        and cached_data.get("property_id") == property_id
                        and cached_data.get("year") == year
                        and cached_data.get("month") == month
                    ):
                        return cached_data
                    else:
                        logger.warning(
                            f"Cache identity mismatch for key '{cache_key}': "
                            f"expected ({tenant_id}, {property_id}, {year}, {month}), "
                            f"found ({cached_data.get('tenant_id')}, {cached_data.get('property_id')}, "
                            f"{cached_data.get('year')}, {cached_data.get('month')}). Ignoring and recalculating."
                        )
    except Exception as e:
        logger.warning(f"Cache read error for {cache_key}: {e}")

    # 2. Calculate revenue from reservation service
    result = await calculate_monthly_revenue(
        property_id=property_id,
        tenant_id=tenant_id,
        year=year,
        month=month
    )

    # 3. Store in cache for 5 minutes (300 seconds)
    try:
        if client is not None:
            if hasattr(client, "_serialize_data"):
                await client.set(cache_key, result, ttl=300)
            elif hasattr(client, "setex"):
                await client.setex(cache_key, 300, json.dumps(result))
            elif hasattr(client, "set"):
                await client.set(cache_key, json.dumps(result), ex=300)
    except Exception as e:
        logger.warning(f"Cache write error for {cache_key}: {e}")

    return result
