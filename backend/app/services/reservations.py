import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

async def calculate_monthly_revenue(property_id: str, month: int, year: int, db_session=None) -> Decimal:
    """
    Calculates revenue for a specific month.
    """

    start_date = datetime(year, month, 1)
    if month < 12:
        end_date = datetime(year, month + 1, 1)
    else:
        end_date = datetime(year + 1, 1, 1)
        
    print(f"DEBUG: Querying revenue for {property_id} from {start_date} to {end_date}")

    # SQL Simulation (This would be executed against the actual DB)
    query = """
        SELECT SUM(total_amount) as total
        FROM reservations
        WHERE property_id = $1
        AND tenant_id = $2
        AND check_in_date >= $3
        AND check_in_date < $4
    """
    
    # In production this query executes against a database session.
    # result = await db.fetch_val(query, property_id, tenant_id, start_date, end_date)
    # return result or Decimal('0')
    
    return Decimal('0') # Placeholder for now until DB connection is finalized

async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    try:
        # Use the shared pool. Constructing a DatabasePool per request opened a
        # fresh 20-connection pool every call and never disposed of it.
        from app.core.database_pool import db_pool

        await db_pool.initialize()

        async with db_pool.get_session() as session:
            # Use SQLAlchemy text for raw SQL
            from sqlalchemy import text
            
            # Round each reservation to cents BEFORE summing. total_amount is
            # NUMERIC(10,3), so summing at full precision and rounding once at
            # the end disagrees with the client, who adds up invoices that were
            # each charged to the cent: 333.333 + 333.333 + 333.334 reports as
            # 1000.00 here but 999.99 in their books. Round at the point revenue
            # is recognised - per reservation - so both sides agree.
            query = text("""
                SELECT 
                    property_id,
                    SUM(ROUND(total_amount, 2)) as total_revenue,
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
                # Decimal throughout: money must never pass through a float.
                total_revenue = Decimal(str(row.total_revenue)).quantize(Decimal("0.01"))
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
    except Exception:
        # A data-layer failure must never be answered with a number. Returning
        # fabricated revenue here is what let a dead connection pool look like
        # a working dashboard for both clients.
        logger.exception(
            "Revenue query failed for property=%s tenant=%s", property_id, tenant_id
        )
        raise
