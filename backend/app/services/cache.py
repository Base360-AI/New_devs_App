from typing import Dict, Any
from app.core.redis_client import redis_client

async def get_revenue_summary(property_id: str, tenant_id: str, month: int = None, year: int = None) -> Dict[str, Any]:
    cache_key = f"revenue:{tenant_id}:{property_id}:{month or 'all'}:{year or 'all'}"

    # Try to get from cache if Redis is available
    if redis_client.is_connected:
        cached = await redis_client.get(cache_key)
        if cached:
            return cached

    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import calculate_revenue

    # Calculate revenue
    result = await calculate_revenue(property_id, tenant_id, month, year)

    # Cache the result for 5 minutes if Redis is available
    if redis_client.is_connected:
        await redis_client.set(cache_key, result, ttl=300)

    return result
