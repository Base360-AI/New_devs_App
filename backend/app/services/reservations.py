from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List

async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Decimal:
    """
    Calculates revenue for a specific month.
    Check-ins are bucketed by the property's local timezone, not UTC.
    """
    from sqlalchemy import text
    from app.core.database_pool import db_pool

    await db_pool.initialize()
    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available")

    query = text("""
        SELECT COALESCE(SUM(r.total_amount), 0) AS total
        FROM reservations r
        JOIN properties p
          ON p.id = r.property_id AND p.tenant_id = r.tenant_id
        WHERE r.property_id = :property_id
          AND r.tenant_id = :tenant_id
          AND (r.check_in_date AT TIME ZONE p.timezone) >= make_timestamp(:year, :month, 1, 0, 0, 0)
          AND (r.check_in_date AT TIME ZONE p.timezone) <  make_timestamp(:year, :month, 1, 0, 0, 0) + INTERVAL '1 month'
    """)

    async with db_pool.get_session() as session:
        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "month": month,
            "year": year
        })
        total = result.scalar_one()

    return Decimal(str(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    from sqlalchemy import text
    from app.core.database_pool import db_pool

    await db_pool.initialize()
    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available")

    async with db_pool.get_session() as session:
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
        total_revenue = Decimal(str(row.total_revenue)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
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
