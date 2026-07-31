import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

UTC = ZoneInfo("UTC")


async def _get_property_timezone(property_id: str, tenant_id: str) -> str:
    """Looks up the property's local timezone (falls back to UTC if unavailable)."""
    try:
        from app.core.database_pool import db_pool

        await db_pool.initialize()

        if db_pool.session_factory:
            async with db_pool.get_session() as session:
                from sqlalchemy import text

                query = text(
                    "SELECT timezone FROM properties WHERE id = :property_id AND tenant_id = :tenant_id"
                )
                result = await session.execute(query, {"property_id": property_id, "tenant_id": tenant_id})
                row = result.fetchone()
                if row and row.timezone:
                    return row.timezone
    except Exception as e:
        logger.warning("Could not resolve timezone for %s (tenant: %s): %s", property_id, tenant_id, e)

    return "UTC"


async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int, db_session=None) -> Decimal:
    """
    Calculates revenue for a specific month.

    Reservations are stored in UTC (check_in_date), but "month" is a concept
    defined in the property's local timezone. Month boundaries are computed
    in the property's local timezone and converted to UTC before filtering,
    so a check-in that is late-night on the last day of a month locally isn't
    miscounted into the wrong month just because it crossed a UTC day boundary.
    """
    property_timezone = await _get_property_timezone(property_id, tenant_id)
    local_tz = ZoneInfo(property_timezone)

    start_date = datetime(year, month, 1, tzinfo=local_tz).astimezone(UTC)
    if month < 12:
        end_date = datetime(year, month + 1, 1, tzinfo=local_tz).astimezone(UTC)
    else:
        end_date = datetime(year + 1, 1, 1, tzinfo=local_tz).astimezone(UTC)

    logger.debug(
        "Querying %s/%s (tz=%s) from %s to %s", tenant_id, property_id, property_timezone, start_date, end_date
    )

    from app.core.database_pool import db_pool
    from sqlalchemy import text

    await db_pool.initialize()

    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available")

    query = text("""
        SELECT SUM(total_amount) as total
        FROM reservations
        WHERE property_id = :property_id
        AND tenant_id = :tenant_id
        AND check_in_date >= :start_date
        AND check_in_date < :end_date
    """)

    async with db_pool.get_session() as session:
        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_date": start_date,
            "end_date": end_date,
        })
        total = result.scalar()

    return Decimal(str(total)) if total is not None else Decimal('0')

async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    # Use the shared pool singleton - constructing DatabasePool() per call built a
    # brand new engine (and connection pool) on every request.
    from app.core.database_pool import db_pool

    await db_pool.initialize()

    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available")

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

        # No reservations for this property within this tenant.
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": "0.00",
            "currency": "USD",
            "count": 0
        }
