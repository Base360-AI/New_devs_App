from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List
import logging
from sqlalchemy import text
from app.core.database_pool import db_pool

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

async def calculate_total_revenue(property_id: str, tenant_id: str, year: int, month: int) -> Dict[str, Any]:
    
    """
    Calculate monthly revenue for one tenant's property.

    March 2024 is the default reporting period for this assignment.
    """
    
    # Initialize the shared database pool when needed.
    if db_pool.session_factory is None:
        await db_pool.initialize()

    if db_pool.session_factory is None:
        raise RuntimeError("Database pool is unavailable")

    session = await db_pool.get_session()

    try:
        result = await session.execute(
            text(
                """
                SELECT
                    COALESCE(SUM(r.total_amount), 0) AS total_revenue,
                    COUNT(*) AS reservation_count
                FROM reservations AS r
                JOIN properties AS p
                  ON p.id = r.property_id
                 AND p.tenant_id = r.tenant_id
                WHERE r.property_id = :property_id
                  AND r.tenant_id = :tenant_id

                  -- CHANGED:
                  -- Convert the reservation time into the property's
                  -- local timezone before checking the month and year.
                  AND EXTRACT(
                        YEAR FROM
                        r.check_in_date AT TIME ZONE p.timezone
                      ) = :year

                  AND EXTRACT(
                        MONTH FROM
                        r.check_in_date AT TIME ZONE p.timezone
                      ) = :month
                """
            ),
            {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "year": year,
                "month": month,
            },
        )

        row = result.one()

        total_revenue = Decimal(str(row.total_revenue))

        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": str(total_revenue),
            "currency": "USD",
            "count": row.reservation_count,
        }

    except Exception:
        # CHANGED:
        # Do not return hardcoded fake financial data.
        # Let the API report the actual database failure.
        raise

    finally:
        await session.close()