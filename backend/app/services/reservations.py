from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List

import pytz


async def _get_property_timezone(session, property_id: str, tenant_id: str) -> str:
    """Look up a property's IANA timezone (e.g. 'Europe/Paris'); default to UTC."""
    from sqlalchemy import text

    tz_row = (
        await session.execute(
            text(
                "SELECT timezone FROM properties "
                "WHERE id = :property_id AND tenant_id = :tenant_id"
            ),
            {"property_id": property_id, "tenant_id": tenant_id},
        )
    ).fetchone()
    return tz_row.timezone if tz_row and tz_row.timezone else "UTC"


def _utc_month_bounds(tz_name: str, month: int, year: int):
    """
    Build the [start, end) UTC instants for a calendar month *as observed in the
    property's local timezone*.

    The bug: the old code built naive datetimes (datetime(year, month, 1)) and
    compared them against check_in_date, which is a timestamptz stored in UTC.
    For a property in Europe/Paris, March starts at 2024-03-01 00:00 *Paris*
    time, i.e. 2024-02-29 23:00 UTC. A reservation checking in at
    2024-02-29 23:30 UTC is March 1st 00:30 locally -- it belongs to March, but
    the naive UTC window (>= 2024-03-01 00:00 UTC) excludes it, so it silently
    falls into February. That is why Client A's March total didn't match their
    books. Fix: anchor the month window to the property's local timezone, then
    convert the boundaries to UTC for the comparison.
    """
    tz = pytz.timezone(tz_name)
    start_local = tz.localize(datetime(year, month, 1))
    if month < 12:
        end_local = tz.localize(datetime(year, month + 1, 1))
    else:
        end_local = tz.localize(datetime(year + 1, 1, 1))
    return start_local.astimezone(pytz.UTC), end_local.astimezone(pytz.UTC)


async def calculate_monthly_revenue(
    property_id: str, tenant_id: str, month: int, year: int, db_session=None
) -> Decimal:
    """
    Calculates revenue for a specific month, bucketing reservations by the
    property's *local* calendar month (not the server/UTC month).
    """
    try:
        from app.core.database_pool import DatabasePool
        from sqlalchemy import text

        db_pool = DatabasePool()
        await db_pool.initialize()
        if not db_pool.session_factory:
            raise Exception("Database pool not available")

        async with db_pool.get_session() as session:
            tz_name = await _get_property_timezone(session, property_id, tenant_id)
            start_utc, end_utc = _utc_month_bounds(tz_name, month, year)

            print(
                f"DEBUG: Querying {property_id}/{tenant_id} ({tz_name}) for "
                f"{year}-{month:02d}: UTC window [{start_utc}, {end_utc})"
            )

            query = text("""
                SELECT SUM(total_amount) AS total
                FROM reservations
                WHERE property_id = :property_id
                  AND tenant_id = :tenant_id
                  AND check_in_date >= :start_utc
                  AND check_in_date < :end_utc
            """)
            row = (
                await session.execute(
                    query,
                    {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "start_utc": start_utc,
                        "end_utc": end_utc,
                    },
                )
            ).fetchone()

            return Decimal(str(row.total)) if row and row.total is not None else Decimal("0")
    except Exception as e:
        print(f"Monthly revenue error for {property_id} (tenant: {tenant_id}): {e}")
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
