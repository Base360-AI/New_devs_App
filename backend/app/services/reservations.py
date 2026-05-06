import logging
from decimal import Decimal
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


async def calculate_total_revenue(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Aggregates revenue from the database.

    If both ``month`` and ``year`` are provided, only reservations whose
    ``check_in_date`` falls inside that calendar month are counted,
    evaluated in the property's own timezone. This is what customers
    expect: a check-in at 2024-03-01 00:30 Europe/Paris counts as
    March, even though its UTC value is 2024-02-29 23:30.

    Without ``month``/``year`` the all-time revenue is returned
    (kept for backwards compatibility with callers that don't yet
    pass a period).
    """
    try:
        from app.core.database_pool import DatabasePool

        db_pool = DatabasePool()
        await db_pool.initialize()

        if not db_pool.session_factory:
            raise Exception("Database pool not available")

        async with db_pool.get_session() as session:
            from sqlalchemy import text

            params: Dict[str, Any] = {
                "property_id": property_id,
                "tenant_id": tenant_id,
            }

            if month and year:
                # Filter using the property's local timezone so that
                # cross-midnight reservations land in the correct month.
                query = text("""
                    SELECT
                        SUM(r.total_amount) AS total_revenue,
                        COUNT(*) AS reservation_count
                    FROM reservations r
                    JOIN properties p
                      ON p.id = r.property_id
                     AND p.tenant_id = r.tenant_id
                    WHERE r.property_id = :property_id
                      AND r.tenant_id = :tenant_id
                      AND (r.check_in_date AT TIME ZONE p.timezone)
                          >= make_date(:year, :month, 1)
                      AND (r.check_in_date AT TIME ZONE p.timezone)
                          <  make_date(:year, :month, 1) + INTERVAL '1 month'
                """)
                params["year"] = year
                params["month"] = month
            else:
                query = text("""
                    SELECT
                        SUM(total_amount) AS total_revenue,
                        COUNT(*) AS reservation_count
                    FROM reservations
                    WHERE property_id = :property_id
                      AND tenant_id = :tenant_id
                """)

            result = await session.execute(query, params)
            row = result.fetchone()

            total = (
                Decimal(str(row.total_revenue))
                if row and row.total_revenue is not None
                else Decimal("0")
            )
            count = row.reservation_count if row else 0

            return {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "total": str(total),
                "currency": "USD",
                "count": count,
            }

    except Exception as e:
        logger.error(
            f"Failed to compute revenue for {property_id} "
            f"(tenant: {tenant_id}): {e}"
        )
        raise
