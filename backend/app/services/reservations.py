from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any
from zoneinfo import ZoneInfo


def format_money(amount: Decimal) -> str:
    return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

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
    Aggregates March 2024 revenue from database using the property's local timezone.
    """
    try:
        # Import database pool
        from app.core.database_pool import DatabasePool
        from sqlalchemy import text
        
        # Initialize pool if needed
        db_pool = DatabasePool()
        await db_pool.initialize()
        
        if db_pool.session_factory:
            async with db_pool.get_session() as session:
                property_query = text("""
                    SELECT timezone
                    FROM properties
                    WHERE id = :property_id AND tenant_id = :tenant_id
                """)

                property_result = await session.execute(property_query, {
                    "property_id": property_id,
                    "tenant_id": tenant_id
                })
                property_row = property_result.fetchone()

                if not property_row:
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total": "0.00",
                        "currency": "USD",
                        "count": 0
                    }

                property_timezone = ZoneInfo(property_row.timezone or "UTC")
                start_local = datetime(2024, 3, 1, tzinfo=property_timezone)
                end_local = datetime(2024, 4, 1, tzinfo=property_timezone)
                start_utc = start_local.astimezone(timezone.utc)
                end_utc = end_local.astimezone(timezone.utc)
                
                # Previous query summed all reservations for the property regardless of
                # reporting month or property timezone:
                #
                # query = text("""
                #     SELECT
                #         property_id,
                #         SUM(total_amount) as total_revenue,
                #         COUNT(*) as reservation_count
                #     FROM reservations
                #     WHERE property_id = :property_id AND tenant_id = :tenant_id
                #     GROUP BY property_id
                # """)

                query = text("""
                    SELECT 
                        SUM(total_amount) as total_revenue,
                        COUNT(*) as reservation_count,
                        COALESCE(MAX(currency), 'USD') as currency
                    FROM reservations 
                    WHERE property_id = :property_id
                    AND tenant_id = :tenant_id
                    AND check_in_date >= :start_date
                    AND check_in_date < :end_date
                """)
                
                result = await session.execute(query, {
                    "property_id": property_id, 
                    "tenant_id": tenant_id,
                    "start_date": start_utc,
                    "end_date": end_utc
                })
                row = result.fetchone()
                
                if row:
                    total_revenue = Decimal(str(row.total_revenue or "0"))
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total": format_money(total_revenue),
                        "currency": row.currency or "USD",
                        "count": row.reservation_count or 0
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
        print(f"Database error for {property_id} (tenant: {tenant_id}): {e}")
        
        # Previous fallback returned property-only mock data, which could hide
        # tenant isolation bugs because tenants with the same property id received
        # the same fake revenue:
        #
        # mock_data = {
        #     'prop-001': {'total': '1000.00', 'count': 3},
        #     'prop-002': {'total': '4975.50', 'count': 4},
        #     'prop-003': {'total': '6100.50', 'count': 2},
        #     'prop-004': {'total': '1776.50', 'count': 4},
        #     'prop-005': {'total': '3256.00', 'count': 3}
        # }
        raise
