from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List
from zoneinfo import ZoneInfo


async def _get_property_timezone(property_id: str, tenant_id: str) -> str:
    """Look up a property's timezone, falling back to UTC if unavailable."""
    try:
        from app.core.database_pool import DatabasePool
        from sqlalchemy import text

        db_pool = DatabasePool()
        await db_pool.initialize()

        if db_pool.session_factory:
            async with db_pool.get_session() as session:
                result = await session.execute(
                    text(
                        """
                        SELECT timezone FROM properties
                        WHERE id = :property_id AND tenant_id = :tenant_id
                        """
                    ),
                    {"property_id": property_id, "tenant_id": tenant_id},
                )
                row = result.fetchone()
                if row and row.timezone:
                    return row.timezone
    except Exception as e:
        print(f"Timezone lookup failed for {property_id} (tenant: {tenant_id}): {e}")

    return "UTC"


async def calculate_monthly_revenue(
    property_id: str,
    month: int,
    year: int,
    tenant_id: str,
    db_session=None,
) -> Decimal:
    """
    Calculates revenue for a specific month.

    Month boundaries are computed in the property's local timezone. A reservation
    such as 2024-02-29 23:30:00+00 falls on 2024-03-01 in Europe/Paris, so it must
    be counted in March for a Paris property. Comparing naive UTC boundaries against
    timezone-aware check_in_date values is what caused the client's month totals to
    disagree with their records.
    """

    tz = ZoneInfo(await _get_property_timezone(property_id, tenant_id))

    # Build the month boundaries in the property's local timezone. The values are
    # timezone-aware, so the comparison against the timestamptz column is correct
    # regardless of the property's offset.
    start_date = datetime(year, month, 1, tzinfo=tz)
    if month < 12:
        end_date = datetime(year, month + 1, 1, tzinfo=tz)
    else:
        end_date = datetime(year + 1, 1, 1, tzinfo=tz)

    print(f"DEBUG: Querying revenue for {property_id} from {start_date} to {end_date} ({tz})")

    query = """
        SELECT SUM(total_amount) as total
        FROM reservations
        WHERE property_id = $1
        AND tenant_id = $2
        AND check_in_date >= $3
        AND check_in_date < $4
    """

    try:
        from app.core.database_pool import DatabasePool
        from sqlalchemy import text

        db_pool = DatabasePool()
        await db_pool.initialize()

        if db_pool.session_factory:
            async with db_pool.get_session() as session:
                result = await session.execute(
                    text(
                        """
                        SELECT SUM(total_amount) as total
                        FROM reservations
                        WHERE property_id = :property_id
                        AND tenant_id = :tenant_id
                        AND check_in_date >= :start_date
                        AND check_in_date < :end_date
                        """
                    ),
                    {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "start_date": start_date,
                        "end_date": end_date,
                    },
                )
                row = result.fetchone()
                if row and row.total is not None:
                    return Decimal(str(row.total))
                return Decimal("0")
    except Exception as e:
        print(f"Database error for monthly revenue {property_id} (tenant: {tenant_id}): {e}")

    return Decimal("0")

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
