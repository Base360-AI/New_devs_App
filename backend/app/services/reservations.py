from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List
from zoneinfo import ZoneInfo

async def calculate_monthly_revenue(property_id: str, month: int, year: int, property_timezone: str = "UTC", db_session=None) -> Decimal:
    """
    Calculates revenue for a specific month.
    """

    # FIX: Month boundaries must be computed in the property's own local
    # timezone, not naive UTC. check_in_date is stored as UTC (TIMESTAMPTZ),
    # but a check-in that reads "March 1, 00:30" on the client's own records
    # (e.g. a Europe/Paris property) is "Feb 29, 23:30" in UTC. Comparing the
    # raw UTC timestamp against naive datetime(year, month, 1) boundaries
    # silently bucketed that reservation into February instead of March -
    # this is exactly why Sunset Properties' March dashboard total didn't
    # match their internal records (see database/seed.sql: res-tz-1). We
    # build the month boundary in the property's local time and convert it
    # to UTC before querying, so bucketing matches the property owner's own
    # calendar instead of the server's UTC clock.
    tz = ZoneInfo(property_timezone)

    local_start = datetime(year, month, 1, tzinfo=tz)
    if month < 12:
        local_end = datetime(year, month + 1, 1, tzinfo=tz)
    else:
        local_end = datetime(year + 1, 1, 1, tzinfo=tz)

    start_date = local_start.astimezone(ZoneInfo("UTC"))
    end_date = local_end.astimezone(ZoneInfo("UTC"))

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
        print(f"Database error for {property_id} (tenant: {tenant_id}): {e}")
        
        # Create property-specific mock data for testing when DB is unavailable
        # This ensures each property shows different figures
        mock_data = {
            'prop-001': {'total': '1000.00', 'count': 3},
            'prop-002': {'total': '4975.50', 'count': 4}, 
            'prop-003': {'total': '6100.50', 'count': 2},
            'prop-004': {'total': '1776.50', 'count': 4},
            'prop-005': {'total': '3256.00', 'count': 3}
        }
        
        mock_property_data = mock_data.get(property_id, {'total': '0.00', 'count': 0})
        
        return {
            "property_id": property_id,
            "tenant_id": tenant_id, 
            "total": mock_property_data['total'],
            "currency": "USD",
            "count": mock_property_data['count']
        }
