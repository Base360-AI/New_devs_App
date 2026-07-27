import json
import redis.asyncio as redis
from typing import Dict, Any
import os

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

async def get_revenue_summary(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    """
    # Tenant segment isolates clients; trailing segment is reserved for month scoping
    cache_key = f"revenue:{tenant_id}:{property_id}:all"

    # Try to get from cache
    cached = await redis_client.get(cache_key)
    if cached:
        result = json.loads(cached)
        # Tripwire: a mis-keyed entry must fail closed as a miss, never cross tenants
        if result.get("tenant_id") == tenant_id:
            return result
        print(f"Cache tenant mismatch for {cache_key}: expected {tenant_id}, got {result.get('tenant_id')} - treating as miss")
    
    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import calculate_total_revenue
    
    # Calculate revenue
    result = await calculate_total_revenue(property_id, tenant_id)
    
    # Cache the result for 5 minutes
    await redis_client.setex(cache_key, 300, json.dumps(result))
    
    return result
