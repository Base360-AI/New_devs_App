from decimal import Decimal
from typing import Dict, Any

async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Decimal:
    """
    Calculates revenue for a specific month, bucketed by the PROPERTY's local
    timezone (not UTC). Clients book and account in local time: a check-in at
    2024-02-29 23:30 UTC for a Europe/Paris property is March 1st locally and
    must count towards March.
    """
    from app.core.database_pool import DatabasePool
    from sqlalchemy import text

    db_pool = DatabasePool()
    await db_pool.initialize()

    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available - cannot compute revenue")

    async with db_pool.get_session() as session:
        query = text("""
            SELECT COALESCE(SUM(r.total_amount), 0) AS total
            FROM reservations r
            JOIN properties p
              ON p.id = r.property_id AND p.tenant_id = r.tenant_id
            WHERE r.property_id = :property_id
              AND r.tenant_id = :tenant_id
              AND EXTRACT(YEAR  FROM (r.check_in_date AT TIME ZONE p.timezone)) = :year
              AND EXTRACT(MONTH FROM (r.check_in_date AT TIME ZONE p.timezone)) = :month
        """)

        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "year": year,
            "month": month,
        })
        total = result.scalar_one()
        return Decimal(str(total))

async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    # Import database pool
    from app.core.database_pool import DatabasePool

    # Initialize pool if needed
    db_pool = DatabasePool()
    await db_pool.initialize()

    if not db_pool.session_factory:
        # Fail loudly: serving fabricated numbers is worse than an error
        raise RuntimeError("Database pool not available - cannot compute revenue")

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
