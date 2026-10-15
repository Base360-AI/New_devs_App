from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List

async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Dict[str, Any]:
    """
    Calculates revenue for reservations checking in during a month,
    using the property's local time zone for the month boundaries.
    """
    start_date = datetime(year, month, 1)
    if month < 12:
        end_date = datetime(year, month + 1, 1)
    else:
        end_date = datetime(year + 1, 1, 1)

    from app.core.database_pool import db_pool
    from sqlalchemy import text

    await db_pool.initialize()

    # Convert check-in to property-local time before comparing with naive month bounds.
    # e.g. 2024-02-29 23:30 UTC is 2024-03-01 00:30 in Europe/Paris, so it counts in March.
    query = text("""
        SELECT
            COALESCE(SUM(r.total_amount), 0) AS total_revenue,
            COUNT(r.id) AS reservation_count
        FROM reservations r
        JOIN properties p ON p.id = r.property_id AND p.tenant_id = r.tenant_id
        WHERE r.property_id = :property_id
        AND r.tenant_id = :tenant_id
        AND (r.check_in_date AT TIME ZONE p.timezone) >= :start_date
        AND (r.check_in_date AT TIME ZONE p.timezone) < :end_date
    """)

    async with db_pool.get_session() as session:
        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_date": start_date,
            "end_date": end_date,
        })
        row = result.fetchone()

    total = Decimal(str(row.total_revenue)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": str(total),
        "currency": "USD",
        "count": row.reservation_count,
    }

async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    try:
        # Reuse the shared pool instead of creating one per request.
        from app.core.database_pool import db_pool

        await db_pool.initialize()
        
        if db_pool.session_factory:
            async with db_pool.get_session() as session:
                # Use SQLAlchemy text for raw SQL
                from sqlalchemy import text
                
                query = text("""
                    SELECT 
                        property_id,
                        SUM(total_amount) as total_revenue,
                        COUNT(*) as reservation_count
                    FROM reservations 
                    WHERE property_id = :property_id AND tenant_id = :tenant_id
                    GROUP BY property_id
                """)
                
                result = await session.execute(query, {
                    "property_id": property_id, 
                    "tenant_id": tenant_id
                })
                row = result.fetchone()
                
                if row:
                    # Amounts are stored to 3 decimals; round once, to cents, after summing.
                    total_revenue = Decimal(str(row.total_revenue)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total": str(total_revenue),
                        "currency": "USD", 
                        "count": row.reservation_count
                    }
                else:
                    # No reservations found for this property
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total": "0.00",
                        "currency": "USD",
                        "count": 0
                    }
        else:
            raise Exception("Database pool not available")
            
    except Exception as e:
        # Fail loudly: returning placeholder figures hides outages behind wrong numbers.
        print(f"Database error for {property_id} (tenant: {tenant_id}): {e}")
        raise
