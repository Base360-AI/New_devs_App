from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo
import logging

logger = logging.getLogger(__name__)

def month_bounds(year: int, month: int, timezone: str) -> Tuple[datetime, datetime]:
    """Half-open [start, end) bounds of a calendar month in the property's
    local timezone, so a 00:30 check-in on the 1st in Paris counts for that
    month even though it is still the previous month in UTC."""
    tz = ZoneInfo(timezone)
    start = datetime(year, month, 1, tzinfo=tz)
    end = datetime(year + 1, 1, 1, tzinfo=tz) if month == 12 else datetime(year, month + 1, 1, tzinfo=tz)
    return start, end


class RevenueUnavailableError(Exception):
    """Raised when revenue cannot be read from the database."""


class PropertyNotFoundError(Exception):
    """Raised when the property does not exist for the requesting tenant."""


class MixedCurrencyError(Exception):
    """Raised when a property's reservations use more than one currency."""


CENTS = Decimal("0.01")


def to_money(amount) -> str:
    """Round once, at the API boundary, to cents (half-up) and serialize as a
    fixed-point string so no float ever touches the value."""
    return str(Decimal(amount or 0).quantize(CENTS, rounding=ROUND_HALF_UP))


async def calculate_total_revenue(
    property_id: str, tenant_id: str, year: Optional[int] = None, month: Optional[int] = None
) -> Dict[str, Any]:
    """
    Aggregates revenue from database: all-time, or for one calendar month
    (in the property's timezone) when year and month are given.

    Raises RevenueUnavailableError instead of returning placeholder figures:
    showing made-up numbers to a client is worse than showing an error.
    """
    # Shared pool, initialized once at app startup
    from app.core.database_pool import db_pool

    if not db_pool.session_factory:
        raise RevenueUnavailableError("Database pool not available")

    try:
        async with db_pool.get_session() as session:
            # Use SQLAlchemy text for raw SQL
            from sqlalchemy import text

            # Property IDs are only unique per tenant: check ownership first
            owned = await session.execute(
                text("SELECT timezone FROM properties WHERE id = :property_id AND tenant_id = :tenant_id"),
                {"property_id": property_id, "tenant_id": tenant_id},
            )
            property_row = owned.first()
            property_found = property_row is not None

            start = end = None
            if property_found and year and month:
                start, end = month_bounds(year, month, property_row.timezone)

            query = text("""
                SELECT
                    currency,
                    SUM(total_amount) as total_revenue,
                    COUNT(*) as reservation_count
                FROM reservations
                WHERE property_id = :property_id AND tenant_id = :tenant_id
                  AND (CAST(:start AS timestamptz) IS NULL OR check_in_date >= :start)
                  AND (CAST(:end AS timestamptz) IS NULL OR check_in_date < :end)
                GROUP BY currency
            """)

            result = await session.execute(query, {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "start": start,
                "end": end,
            })
            rows = result.fetchall()
    except Exception as e:
        logger.exception(f"Revenue query failed for {property_id} (tenant: {tenant_id})")
        raise RevenueUnavailableError(str(e)) from e

    if not property_found:
        raise PropertyNotFoundError(property_id)

    if len(rows) > 1:
        # Summing amounts in different currencies would produce a meaningless total
        raise MixedCurrencyError(property_id)

    if rows:
        row = rows[0]
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": to_money(row.total_revenue),
            "currency": row.currency,
            "count": row.reservation_count
        }

    # No reservations found for this property
    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": to_money(0),
        "currency": "USD",
        "count": 0
    }


async def list_properties(tenant_id: str) -> List[Dict[str, str]]:
    """Properties owned by the tenant, for the dashboard's property selector."""
    from app.core.database_pool import db_pool

    if not db_pool.session_factory:
        raise RevenueUnavailableError("Database pool not available")

    try:
        async with db_pool.get_session() as session:
            from sqlalchemy import text

            result = await session.execute(
                text("SELECT id, name FROM properties WHERE tenant_id = :tenant_id ORDER BY name"),
                {"tenant_id": tenant_id},
            )
            rows = result.fetchall()
    except Exception as e:
        logger.exception(f"Property list query failed (tenant: {tenant_id})")
        raise RevenueUnavailableError(str(e)) from e

    return [{"id": row.id, "name": row.name} for row in rows]
