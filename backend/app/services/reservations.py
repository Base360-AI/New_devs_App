from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, Optional
import logging

from sqlalchemy import text

from app.core.database_pool import db_pool

logger = logging.getLogger(__name__)

# Money is rounded exactly once, at the very end of the aggregation.
CENTS = Decimal("0.01")


class RevenueUnavailableError(RuntimeError):
    """Raised when revenue cannot be computed from the database."""


def _month_bounds(month: int, year: int) -> tuple[datetime, datetime]:
    """
    Returns the [start, end) bounds of a month as *naive local wall-clock* datetimes.

    These are deliberately naive: they are compared against
    `check_in_date AT TIME ZONE property.timezone`, i.e. against the local time at
    the property. A stay that starts on 2024-02-29 23:30 UTC starts on
    2024-03-01 00:30 in Europe/Paris, so it belongs to the client's March, not February.
    """
    start = datetime(year, month, 1)
    if month < 12:
        end = datetime(year, month + 1, 1)
    else:
        end = datetime(year + 1, 1, 1)
    return start, end


async def _fetch_revenue(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Aggregates reservation revenue for one property of one tenant.

    Two things make this query correct:

    1. It joins properties on BOTH (id, tenant_id) and filters reservations on
       tenant_id. Property IDs are only unique within a tenant, so filtering on
       property_id alone would mix two different buildings owned by two different
       companies.
    2. Month filtering happens on the property's local calendar
       (`check_in_date AT TIME ZONE p.timezone`), not on UTC.
    """
    await db_pool.ensure_initialized()

    if not db_pool.session_factory:
        raise RevenueUnavailableError("Database pool is not available")

    period_filter = ""
    params: Dict[str, Any] = {"property_id": property_id, "tenant_id": tenant_id}

    if month and year:
        period_start, period_end = _month_bounds(month, year)
        period_filter = """
              AND (r.check_in_date AT TIME ZONE p.timezone) >= CAST(:period_start AS timestamp)
              AND (r.check_in_date AT TIME ZONE p.timezone) <  CAST(:period_end   AS timestamp)
        """
        params["period_start"] = period_start
        params["period_end"] = period_end

    query = text(
        f"""
        SELECT
            COALESCE(SUM(r.total_amount), 0) AS total_revenue,
            COUNT(*)                         AS reservation_count,
            COUNT(DISTINCT r.currency)       AS currency_count,
            MIN(r.currency)                  AS currency,
            MIN(p.timezone)                  AS property_timezone
        FROM reservations r
        JOIN properties p
          ON p.id = r.property_id
         AND p.tenant_id = r.tenant_id
        WHERE r.property_id = :property_id
          AND r.tenant_id   = :tenant_id
          {period_filter}
        """
    )

    async with db_pool.session() as session:
        result = await session.execute(query, params)
        row = result.fetchone()

    # Aggregates without GROUP BY always return exactly one row, even for no matches.
    raw_total = Decimal(str(row.total_revenue))
    count = int(row.reservation_count)

    if row.currency_count and row.currency_count > 1:
        # Summing mixed currencies produces a meaningless number; refuse instead.
        raise RevenueUnavailableError(
            f"Property {property_id} has reservations in {row.currency_count} different "
            f"currencies; a single total cannot be computed."
        )

    # SUM at full NUMERIC(10,3) precision first, round to cents exactly once.
    # Rounding each reservation first would turn 333.333 + 333.333 + 333.334
    # into 999.99 instead of 1000.00.
    total = raw_total.quantize(CENTS, rounding=ROUND_HALF_UP)

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": str(total),
        "currency": row.currency or "USD",
        "count": count,
        "timezone": row.property_timezone,
    }


async def calculate_monthly_revenue(
    property_id: str,
    tenant_id: str,
    month: int,
    year: int,
) -> Decimal:
    """
    Calculates revenue for a specific month, on the property's local calendar.
    """
    summary = await _fetch_revenue(property_id, tenant_id, month=month, year=year)
    return Decimal(summary["total"])


async def calculate_total_revenue(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Aggregates revenue from database, optionally narrowed to a single month.
    """
    if not tenant_id:
        raise ValueError("tenant_id is required to compute revenue")

    return await _fetch_revenue(property_id, tenant_id, month=month, year=year)
