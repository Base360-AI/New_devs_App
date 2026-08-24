from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List

from sqlalchemy import text

async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Decimal:
    """
    Calculates revenue for a specific month, in the property's own timezone.
    """
    # Import database pool
    from app.core.database_pool import DatabasePool

    # Initialize pool if needed
    db_pool = DatabasePool()
    await db_pool.initialize()

    if not db_pool.session_factory:
        raise Exception("Database pool not available")

    async with db_pool.get_session() as session:
        # Use SQLAlchemy text for raw SQL
        from sqlalchemy import text

        # Month boundaries belong to the property's local timezone, not UTC.
        # A Paris check-in at 2024-02-29 23:30 UTC is 2024-03-01 00:30 locally
        # and therefore counts towards March, not February.
        query = text("""
            SELECT COALESCE(SUM(r.total_amount), 0) as total
            FROM reservations r
            JOIN properties p
              ON p.id = r.property_id AND p.tenant_id = r.tenant_id
            WHERE r.property_id = :property_id
              AND r.tenant_id = :tenant_id
              AND (r.check_in_date AT TIME ZONE p.timezone) >= make_timestamp(:year, :month, 1, 0, 0, 0)
              AND (r.check_in_date AT TIME ZONE p.timezone) <  make_timestamp(:year, :month, 1, 0, 0, 0) + interval '1 month'
        """)

        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "year": year,
            "month": month
        })
        row = result.fetchone()

        return Decimal(str(row.total))

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
        raise
