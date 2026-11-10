import logging
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

CENT = Decimal("0.01")


def _to_cents(value) -> Decimal:
    """
    Round a money amount to cents.

    total_amount is NUMERIC(10,3), so sums can carry sub-cent digits.
    Sum exactly in the database, then round once here with ROUND_HALF_UP
    (never through float, which cannot represent most decimal values).
    """
    return Decimal(str(value if value is not None else 0)).quantize(CENT, rounding=ROUND_HALF_UP)

async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Dict[str, Any]:
    """
    Calculates revenue for a calendar month in the property's own timezone.

    check_in_date is stored in UTC. A booking at 2024-02-29 23:30 UTC is
    2024-03-01 00:30 in Europe/Paris, so for a Paris property it belongs to
    March. Month boundaries are therefore applied to the local check-in time.
    """
    # Naive local-time bounds; compared against check_in_date converted to the
    # property's timezone (timestamptz AT TIME ZONE tz -> local timestamp).
    start_date = datetime(year, month, 1)
    if month < 12:
        end_date = datetime(year, month + 1, 1)
    else:
        end_date = datetime(year + 1, 1, 1)

    from app.core.database_pool import db_pool
    from sqlalchemy import text

    await db_pool.initialize()
    if not db_pool.session_factory:
        raise Exception("Database pool not available")

    query = text("""
        SELECT
            COALESCE(SUM(r.total_amount), 0) AS total_revenue,
            COUNT(r.id) AS reservation_count
        FROM reservations r
        JOIN properties p
          ON p.id = r.property_id AND p.tenant_id = r.tenant_id
        WHERE r.property_id = :property_id
          AND r.tenant_id = :tenant_id
          AND (r.check_in_date AT TIME ZONE p.timezone) >= :start_date
          AND (r.check_in_date AT TIME ZONE p.timezone) < :end_date
    """)

    try:
        async with db_pool.get_session() as session:
            result = await session.execute(query, {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "start_date": start_date,
                "end_date": end_date,
            })
            row = result.fetchone()
    except Exception as e:
        logger.error(f"Database error for {property_id} (tenant: {tenant_id}, {year}-{month:02d}): {e}")
        raise

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": str(_to_cents(row.total_revenue)),
        "currency": "USD",
        "count": row.reservation_count,
    }

async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    try:
        # Reuse the process-wide pool instead of creating one per request
        from app.core.database_pool import db_pool

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
                    total_revenue = _to_cents(row.total_revenue)
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
        # Never return made-up figures: a financial dashboard must fail loudly
        # instead of showing numbers that belong to no tenant.
        logger.error(f"Database error for {property_id} (tenant: {tenant_id}): {e}")
        raise
