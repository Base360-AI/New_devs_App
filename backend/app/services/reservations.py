import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict

from sqlalchemy import text

from app.core.database_pool import DatabasePool

logger = logging.getLogger(__name__)


async def calculate_monthly_revenue(
    property_id: str,
    tenant_id: str,
    month: int,
    year: int,
) -> Dict[str, Any]:
    """Aggregate revenue for a single calendar month, anchored at UTC midnight."""
    # Per-property local-timezone boundaries are a future enhancement;
    # for now the month window is UTC-based and explicit.
    start_date = datetime(year, month, 1, tzinfo=timezone.utc)
    end_date = (
        datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        if month == 12
        else datetime(year, month + 1, 1, tzinfo=timezone.utc)
    )

    db_pool = DatabasePool()
    await db_pool.initialize()
    if not db_pool.session_factory:
        raise RuntimeError("Database pool not initialized")

    async with db_pool.get_session() as session:
        result = await session.execute(
            text(
                """
                SELECT
                    COALESCE(SUM(total_amount), 0) AS total_revenue,
                    COUNT(*) AS reservation_count
                FROM reservations
                WHERE property_id = :property_id
                  AND tenant_id = :tenant_id
                  AND check_in_date >= :start_date
                  AND check_in_date < :end_date
                """
            ),
            {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "start_date": start_date,
                "end_date": end_date,
            },
        )
        row = result.fetchone()

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "month": month,
        "year": year,
        "total": str(Decimal(str(row.total_revenue))),
        "currency": "USD",
        "count": row.reservation_count,
    }


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """Aggregate all-time revenue for a (property, tenant) pair."""
    db_pool = DatabasePool()
    await db_pool.initialize()
    if not db_pool.session_factory:
        raise RuntimeError("Database pool not initialized")

    async with db_pool.get_session() as session:
        result = await session.execute(
            text(
                """
                SELECT
                    COALESCE(SUM(total_amount), 0) AS total_revenue,
                    COUNT(*) AS reservation_count
                FROM reservations
                WHERE property_id = :property_id
                  AND tenant_id = :tenant_id
                """
            ),
            {"property_id": property_id, "tenant_id": tenant_id},
        )
        row = result.fetchone()

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": str(Decimal(str(row.total_revenue))),
        "currency": "USD",
        "count": row.reservation_count,
    }
