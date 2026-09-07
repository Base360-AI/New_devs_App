import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict
from zoneinfo import ZoneInfo

from sqlalchemy import text

logger = logging.getLogger(__name__)


async def calculate_monthly_revenue(
    property_id: str,
    tenant_id: str,
    month: int,
    year: int,
    db_session,
) -> Decimal:
    """Calculate revenue for a property during its local calendar month."""

    if db_session is None:
        raise ValueError("db_session is required")

    property_result = await db_session.execute(
        text("""
            SELECT timezone
            FROM properties
            WHERE id = :property_id
              AND tenant_id = :tenant_id
        """),
        {
            "property_id": property_id,
            "tenant_id": tenant_id,
        },
    )

    property_row = property_result.fetchone()

    if property_row is None:
        return Decimal("0")

    property_timezone = ZoneInfo(property_row.timezone)

    local_start = datetime(
        year,
        month,
        1,
        tzinfo=property_timezone,
    )

    if month == 12:
        local_end = datetime(
            year + 1,
            1,
            1,
            tzinfo=property_timezone,
        )
    else:
        local_end = datetime(
            year,
            month + 1,
            1,
            tzinfo=property_timezone,
        )

    result = await db_session.execute(
        text("""
            SELECT COALESCE(SUM(total_amount), 0) AS total
            FROM reservations
            WHERE property_id = :property_id
              AND tenant_id = :tenant_id
              AND check_in_date >= :start_date
              AND check_in_date < :end_date
        """),
        {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_date": local_start.astimezone(timezone.utc),
            "end_date": local_end.astimezone(timezone.utc),
        },
    )

    row = result.fetchone()

    if row is None or row.total is None:
        return Decimal("0")

    return Decimal(str(row.total))


async def calculate_total_revenue(
    property_id: str,
    tenant_id: str,
) -> Dict[str, Any]:
    """Calculate all-time revenue for one tenant property."""

    from app.core.database_pool import DatabasePool

    db_pool = DatabasePool()
    await db_pool.initialize()

    if not db_pool.session_factory:
        raise RuntimeError("Database pool is not available")

    try:
        async with db_pool.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT
                        COALESCE(SUM(total_amount), 0) AS total_revenue,
                        COUNT(*) AS reservation_count
                    FROM reservations
                    WHERE property_id = :property_id
                      AND tenant_id = :tenant_id
                """),
                {
                    "property_id": property_id,
                    "tenant_id": tenant_id,
                },
            )

            row = result.fetchone()

            return {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "total": str(Decimal(str(row.total_revenue or "0"))),
                "currency": "USD",
                "count": int(row.reservation_count or 0),
            }

    except Exception:
        logger.exception(
            "Revenue query failed for property %s and tenant %s",
            property_id,
            tenant_id,
        )
        raise
    finally:
        await db_pool.close()