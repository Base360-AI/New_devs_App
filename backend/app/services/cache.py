import json
import redis.asyncio as redis
from typing import Dict, Any, Optional
import os

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


async def get_revenue_summary(
    property_id: str,
    tenant_id: str,
    period_type: str = "all",
    month: Optional[int] = None,
    year: Optional[int] = None,
    timezone_str: str = "UTC",
) -> Dict[str, Any]:
    """
    Fetches revenue summary with caching.
    
    Args:
        property_id: The property ID
        tenant_id: The tenant ID
        period_type: "all", "monthly", or "yearly"
        month: Month (1-12) for monthly
        year: Year for monthly/yearly
        timezone_str: Property's timezone
    """
    # Build cache key with all parameters to ensure correct caching
    cache_key = f"revenue:{property_id}:{tenant_id}:{period_type}:{month}:{year}:{timezone_str}"

    # Try to get from cache
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception as e:
        print(f"Redis cache read error: {e}")
        # Continue without cache on error

    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import calculate_total_revenue

    # Calculate revenue with all parameters
    result = await calculate_total_revenue(
        property_id=property_id,
        tenant_id=tenant_id,
        period_type=period_type,
        month=month,
        year=year,
        timezone_str=timezone_str,
    )

    # Cache the result for 5 minutes
    try:
        await redis_client.setex(cache_key, 300, json.dumps(result))
    except Exception as e:
        print(f"Redis cache write error: {e}")

    return result
