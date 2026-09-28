import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict


logger = logging.getLogger(__name__)


class RevenueServiceError(RuntimeError):
    """Raised when revenue data cannot be retrieved from the database."""


class PropertyNotFoundError(LookupError):
    """Raised when a property does not belong to the requesting tenant."""


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
        # Use the application-wide database pool initialized at startup.
        from app.core.database_pool import db_pool
        
        async with db_pool.get_session() as session:
            # Use SQLAlchemy text for raw SQL
            from sqlalchemy import text

            property_query = text("""
                SELECT timezone
                FROM properties
                WHERE id = :property_id AND tenant_id = :tenant_id
                LIMIT 1
            """)
            property_result = await session.execute(property_query, {
                "property_id": property_id,
                "tenant_id": tenant_id
            })

            if property_result.scalar_one_or_none() is None:
                raise PropertyNotFoundError("Property not found")

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

            # No reservations found for this property
            return {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "total": "0.00",
                "currency": "USD",
                "count": 0
            }

    except PropertyNotFoundError:
        raise
    except Exception as error:
        logger.exception(
            "Revenue query failed for tenant=%s property=%s",
            tenant_id,
            property_id,
        )
        raise RevenueServiceError(
            "Revenue data could not be retrieved"
        ) from error
