from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple
from zoneinfo import ZoneInfo


class MixedCurrencyError(Exception):
    """Raised when a total would silently sum amounts in different currencies."""


def month_bounds_utc(month: str, tz_name: str) -> Tuple[datetime, datetime]:
    """Half-open UTC interval [start, end) covering the property-local month.

    Each bound is derived from its own local wall time, so a month containing
    a DST transition gets different UTC offsets at each edge.
    Unrecognised/empty timezones fall back to UTC bucketing rather than failing.
    """
    year, mon = int(month[:4]), int(month[5:7])
    try:
        tz = ZoneInfo(tz_name) if tz_name else timezone.utc
    except Exception:
        print(f"Unrecognised property timezone '{tz_name}' - falling back to UTC bucketing")
        tz = timezone.utc
    start_local = datetime(year, mon, 1, tzinfo=tz)
    if mon < 12:
        end_local = datetime(year, mon + 1, 1, tzinfo=tz)
    else:
        end_local = datetime(year + 1, 1, 1, tzinfo=tz)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)

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

async def calculate_total_revenue(property_id: str, tenant_id: str, month: Optional[str] = None) -> Dict[str, Any]:
    """
    Aggregates revenue from database, optionally scoped to a property-local month (YYYY-MM).
    """
    period = month or "all"
    try:
        # Import database pool
        from app.core.database_pool import DatabasePool
        
        # Initialize pool if needed
        db_pool = DatabasePool()
        await db_pool.initialize()
        
        if db_pool.session_factory:
            async with await db_pool.get_session() as session:
                # Use SQLAlchemy text for raw SQL
                from sqlalchemy import text

                params = {"property_id": property_id, "tenant_id": tenant_id}
                date_filter = ""
                if month:
                    # Bucket by the property's local calendar month, comparing in UTC
                    # so the check_in_date column stays index-friendly
                    tz_result = await session.execute(text("""
                        SELECT timezone FROM properties
                        WHERE id = :property_id AND tenant_id = :tenant_id
                    """), params)
                    tz_row = tz_result.fetchone()
                    tz_name = tz_row.timezone if tz_row else None
                    start_utc, end_utc = month_bounds_utc(month, tz_name)
                    date_filter = " AND check_in_date >= :start_utc AND check_in_date < :end_utc"
                    params.update({"start_utc": start_utc, "end_utc": end_utc})

                query = text(f"""
                    SELECT
                        property_id,
                        SUM(total_amount) as total_revenue,
                        COUNT(*) as reservation_count,
                        COUNT(DISTINCT COALESCE(NULLIF(currency, ''), 'USD')) as currency_count,
                        MIN(COALESCE(NULLIF(currency, ''), 'USD')) as currency
                    FROM reservations
                    WHERE property_id = :property_id AND tenant_id = :tenant_id{date_filter}
                    GROUP BY property_id
                """)

                result = await session.execute(query, params)
                row = result.fetchone()
                
                if row:
                    if row.currency_count > 1:
                        # 100 EUR + 100 USD is not 200 of anything without a
                        # conversion rate and the date that rate applied
                        raise MixedCurrencyError(
                            f"Property {property_id} has reservations in {row.currency_count} "
                            f"currencies for period {period}; refusing to sum without conversion"
                        )
                    total_revenue = Decimal(str(row.total_revenue))
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "period": period,
                        "total": str(total_revenue),
                        "currency": row.currency,
                        "count": row.reservation_count
                    }
                else:
                    # No reservations found for this property; currency falls back
                    # to the schema default since there is nothing to read it from
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "period": period,
                        "total": "0.00",
                        "currency": "USD",
                        "count": 0
                    }
        else:
            raise Exception("Database pool not available")
            
    except MixedCurrencyError:
        raise
    except Exception as e:
        print(f"Database error for {property_id} (tenant: {tenant_id}): {e}")
        # Never substitute fabricated figures for a failed query - propagate instead
        raise
