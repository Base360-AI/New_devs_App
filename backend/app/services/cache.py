from typing import Dict, Any

from app.core.redis_client import redis_client

async def get_revenue_summary(
    property_id: str,
    tenant_id: str,
    month: int | None = None,
    year: int | None = None,
) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    """
    period_key = f"{year:04d}-{month:02d}" if month is not None and year is not None else "all-time"
    cache_key = f"revenue:{tenant_id}:{property_id}:{period_key}"
    
    # Try to get from cache
    cached = await redis_client.get(cache_key)
    if cached:
        return cached
    
    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import calculate_total_revenue
    
    # Calculate revenue
    result = await calculate_total_revenue(property_id, tenant_id, month=month, year=year)
    
    # Cache the result for 5 minutes
    await redis_client.set(cache_key, result, ttl=300)
    
    return result
