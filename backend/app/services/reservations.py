from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, List
from zoneinfo import ZoneInfo

async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int, db_session=None) -> Decimal:
    """
    Calculates revenue for a specific month, as the month falls at the property.
    """

    from app.core.database_pool import DatabasePool
    from sqlalchemy import text

    db_pool = DatabasePool()
    await db_pool.initialize()

    if not db_pool.session_factory:
        raise Exception("Database pool not available")

    async with db_pool.get_session() as session:
        property_timezone = await session.scalar(
            text("SELECT timezone FROM properties WHERE id = :property_id AND tenant_id = :tenant_id"),
            {"property_id": property_id, "tenant_id": tenant_id}
        )

        if property_timezone is None:
            raise ValueError(f"No property {property_id} for tenant {tenant_id}")

        # The month starts at local midnight, not 00:00 UTC: a check-in stored as
        # 2024-02-29 23:30+00 is already 1 March in Europe/Paris.
        tz = ZoneInfo(property_timezone)

        start_date = datetime(year, month, 1, tzinfo=tz).astimezone(timezone.utc)
        if month < 12:
            end_date = datetime(year, month + 1, 1, tzinfo=tz).astimezone(timezone.utc)
        else:
            end_date = datetime(year + 1, 1, 1, tzinfo=tz).astimezone(timezone.utc)

        print(f"DEBUG: Querying revenue for {property_id} from {start_date} to {end_date}")

        query = text("""
            SELECT SUM(total_amount) as total
            FROM reservations
            WHERE property_id = :property_id
            AND tenant_id = :tenant_id
            AND check_in_date >= :start_date
            AND check_in_date < :end_date
        """)

        total = await session.scalar(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_date": start_date,
            "end_date": end_date
        })

    # SUM over no rows is NULL, which is a zero month rather than a missing answer.
    return total if total is not None else Decimal('0.000')

async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    try:
        # Import database pool
        from app.core.database_pool import DatabasePool
        
        # Initialize pool if needed
        db_pool = DatabasePool()
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
                    total_revenue = Decimal(str(row.total_revenue))
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
        # No fallback figures: inventing revenue when the database is unreachable is
        # worse than failing, and it hid this outage until the numbers were queried.
        print(f"Database error for {property_id} (tenant: {tenant_id}): {e}")
        raise
