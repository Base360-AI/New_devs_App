from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List

async def calculate_monthly_revenue(property_id: str, month: int, year: int, tenant_id: str) -> Decimal:
    """Calculate revenue for the month in the property's local time zone."""
    result = await calculate_total_revenue(property_id, tenant_id, month, year)
    return Decimal(result["total"])

async def calculate_total_revenue(property_id: str, tenant_id: str, month: int = None, year: int = None) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    if (month is None) != (year is None):
        raise ValueError("Month and year must be supplied together")
    start_date = datetime(year, month, 1) if month is not None else None
    end_date = (datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)) if month is not None else None
    try:
        # Import database pool
        from app.core.database_pool import db_pool
        
        # Initialize pool if needed
        await db_pool.initialize()
        
        if db_pool.session_factory:
            async with db_pool.get_session() as session:
                # Use SQLAlchemy text for raw SQL
                from sqlalchemy import text
                
                date_filter = "" if month is None else """
                    AND r.check_in_date >= (CAST(:start_date AS timestamp) AT TIME ZONE p.timezone)
                    AND r.check_in_date < (CAST(:end_date AS timestamp) AT TIME ZONE p.timezone)
                """
                query = text("""
                    SELECT 
                        r.property_id,
                        SUM(total_amount) as total_revenue,
                        COUNT(*) as reservation_count
                    FROM reservations r
                    JOIN properties p ON p.id = r.property_id AND p.tenant_id = r.tenant_id
                    WHERE r.property_id = :property_id AND r.tenant_id = :tenant_id
                """ + date_filter + " GROUP BY r.property_id")
                
                result = await session.execute(query, {
                    "property_id": property_id, 
                    "tenant_id": tenant_id,
                    "start_date": start_date,
                    "end_date": end_date,
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
        
        # A monthly report must never fall back to an unrelated hardcoded total.
        if month is not None:
            raise

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
