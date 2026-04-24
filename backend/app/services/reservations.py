from datetime import datetime
from typing import Dict, Any

async def calculate_total_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Dict[str, Any]:
    """
    Aggregates revenue from database securely isolating by tenant and converting to appropriate
    timezones for filtering out bookings per month exactly according to local timezone.
    Returns integer cents to prevent floating point inaccuracies.
    """
    try:
        from app.core.database_pool import db_pool
        
        # Ensure pool is initialized
        if not db_pool.session_factory:
            await db_pool.initialize()
            
        if db_pool.session_factory:
            async with db_pool.get_session() as session:
                from sqlalchemy import text
                
                # We use postgres AT TIME ZONE to shift the timestamptz to the property's local time explicitly.
                # We return integer cents by casting to BIGINT to avoid frontend/backend floating point loss.
                query = text("""
                    SELECT 
                        r.property_id,
                        CAST(COALESCE(SUM(r.total_amount), 0) * 100 AS BIGINT) as total_revenue_cents,
                        COUNT(r.id) as reservation_count
                    FROM reservations r
                    JOIN properties p ON r.property_id = p.id AND r.tenant_id = p.tenant_id
                    WHERE r.property_id = :property_id 
                      AND r.tenant_id = :tenant_id
                      AND EXTRACT(MONTH FROM r.check_in_date AT TIME ZONE p.timezone) = :month
                      AND EXTRACT(YEAR FROM r.check_in_date AT TIME ZONE p.timezone) = :year
                    GROUP BY r.property_id
                """)
                
                result = await session.execute(query, {
                    "property_id": property_id, 
                    "tenant_id": tenant_id,
                    "month": month,
                    "year": year
                })
                row = result.fetchone()
                
                if row:
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total_cents": row.total_revenue_cents,
                        "currency": "USD", 
                        "count": row.reservation_count
                    }
                else:
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total_cents": 0,
                        "currency": "USD",
                        "count": 0
                    }
        else:
            raise Exception("Database pool not available")
            
    except Exception as e:
        print(f"Database error for {property_id} (tenant: {tenant_id}): {e}")
        return {
            "property_id": property_id,
            "tenant_id": tenant_id, 
            "total_cents": 0,
            "currency": "USD",
            "count": 0
        }