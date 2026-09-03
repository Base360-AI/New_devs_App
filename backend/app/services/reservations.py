import logging
from decimal import Decimal
from typing import Any, Dict


logger = logging.getLogger(__name__)


class RevenueDataUnavailableError(RuntimeError):
    """Raised when revenue data cannot be read from PostgreSQL."""


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    try:
        from app.core.database_pool import db_pool

        await db_pool.initialize()
        if not db_pool.session_factory:
            raise RuntimeError("PostgreSQL connection pool is unavailable")

        from sqlalchemy import text

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

            return {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "total": "0.00",
                "currency": "USD",
                "count": 0
            }
    except Exception as error:
        logger.exception(
            "Unable to load revenue for property %s and tenant %s",
            property_id,
            tenant_id,
        )
        raise RevenueDataUnavailableError from error
