from typing import Dict, Any, Optional
from app.core.redis_client import redis_client

def _build_cache_key(property_id: str, tenant_id: str, month: Optional[int], year: Optional[int]) -> str:
    period = f"{year:04d}-{month:02d}" if month is not None and year is not None else "latest"
    return f"revenue:{tenant_id}:{property_id}:{period}"


async def get_revenue_summary(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    """
    cache_key = _build_cache_key(property_id, tenant_id, month, year)
    
    # Try to get from cache
    if redis_client.is_connected:
        try:
            cached = await redis_client.get(cache_key)
            if cached:
                return cached
        except Exception:
            pass
    
    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import calculate_total_revenue
    
    # Calculate revenue
    result = await calculate_total_revenue(property_id, tenant_id, month=month, year=year)
    
    # Cache the result for 5 minutes
    if redis_client.is_connected:
        try:
            result_cache_key = _build_cache_key(
                property_id,
                tenant_id,
                result.get("period_month"),
                result.get("period_year"),
            )
            await redis_client.set(result_cache_key, result, ttl=300)
            if result_cache_key != cache_key:
                await redis_client.set(cache_key, result, ttl=300)
        except Exception:
            pass
    
    return result
