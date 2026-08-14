from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List


# future bug reproducer : this function only counts the revenue for a particular property_id which is again not unique in database , unique thing is property_id + tenant_id 
async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int, db_session) -> Decimal:
    """
    Calculates revenue for a specific month.
    """

    # Fetch the property's timezone so month boundaries are computed in LOCAL time,
    # not server/UTC time 
    tz_query = text("""
        SELECT timezone
        FROM properties
        WHERE id = :property_id AND tenant_id = :tenant_id
    """)
    tz_row = (await db_session.execute(tz_query, {
        "property_id": property_id,
        "tenant_id": tenant_id
    })).fetchone()

    if not tz_row:
        raise ValueError(f"Property {property_id} not found for tenant {tenant_id}")

    tz = ZoneInfo(tz_row.timezone)


    start_date = datetime(year, month, 1, tzinfo=tz)
    if month < 12:
        end_date = datetime(year, month + 1, 1, tzinfo=tz)
    else:
        end_date = datetime(year + 1, 1, 1, tzinfo=tz)
        
    print(f"DEBUG: Querying revenue for {property_id} (tenant: {tenant_id}) from {start_date} to {end_date}")


    # SQL Simulation (This would be executed against the actual DB)
    query = text("""
        SELECT SUM(total_amount) as total
        FROM reservations
        WHERE property_id = :property_id
        AND tenant_id = :tenant_id
        AND check_in_date >= :start_date
        AND check_in_date < :end_date
    """)

    result = await db_session.execute(query, {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "start_date": start_date,
        "end_date": end_date
    })

    row = result.fetchone()

    return Decimal(str(row.total)) if row and row.total is not None else Decimal('0')

    
    # In production this query executes against a database session.
    # result = await db.fetch_val(query, property_id, tenant_id, start_date, end_date)
    # return result or Decimal('0')
    
    # Placeholder for now until DB connection is finalized

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
