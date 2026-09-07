import json
import redis.asyncio as redis
from typing import Dict, Any, Optional
from app.services.reservations import calculate_revenue
import os
import logging

logger = logging.getLogger(__name__)

def revenue_cache_key(tenant_id: str, property_id: str, month: Optional[int] = None, year: Optional[int] = None) -> str:
    """Tenant-isolated, period-scoped key – prevents cross-tenant contamination."""
    if not tenant_id:
        raise ValueError("tenant_id is required")
    period = f"{year:04d}-{month:02d}" if month is not None and year is not None else "all"
    return f"revenue:{tenant_id}:{property_id}:{period}"



# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

async def get_revenue_summary(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Fetches revenue summary from Redis or calculates from DB.
    Returns None if the property does not belong to the tenant.

    """
    cache_key = revenue_cache_key(tenant_id, property_id, month, year)
    
    # Try to get from cache
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            data = json.loads(cached)
            # Defense in depth check
            if data.get("tenant_id") == tenant_id and data.get("property_id") == property_id:
                return data
    except Exception as e:
        logger.warning(f"Redis cache read warning for {cache_key}: {e}")

    
    # Calculate revenue
    result = await calculate_revenue(
    property_id=property_id,
    tenant_id=tenant_id,
    month=month,
    year=year,
)
    if result is None:
        return None
    # Cache the result for 5 minutes
    try:
        await redis_client.setex(cache_key, 300, json.dumps(result, default=str))
    except Exception as e:
        logger.warning(f"Redis cache write warning for {cache_key}: {e}")

    
    return result
