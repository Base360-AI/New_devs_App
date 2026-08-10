from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List


CURRENCY_QUANTUM = Decimal("0.01")


def round_currency_amount(amount: Decimal) -> str:
    """Round an exact decimal amount to cents using commercial rounding."""
    rounded = amount.quantize(CURRENCY_QUANTUM, rounding=ROUND_HALF_UP)
    return format(rounded, ".2f")

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
    from sqlalchemy import text

    from app.core.database_pool import db_pool

    query = text("""
        SELECT
            COALESCE(SUM(total_amount), 0::NUMERIC) as total_revenue,
            COUNT(*) as reservation_count
        FROM reservations
        WHERE property_id = :property_id AND tenant_id = :tenant_id
    """)

    async with db_pool.get_session() as session:
        result = await session.execute(
            query,
            {
                "property_id": property_id,
                "tenant_id": tenant_id,
            },
        )
        row = result.fetchone()

    total_revenue = Decimal(str(row.total_revenue))
    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": round_currency_amount(total_revenue),
        "currency": "USD",
        "count": row.reservation_count,
    }
