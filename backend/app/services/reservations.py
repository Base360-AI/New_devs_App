from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, Optional, Tuple

from sqlalchemy import text

from app.core.database_pool import db_pool

# `check_in_date` is TIMESTAMPTZ, so it comes back in UTC. A booking that checks in at
# 2024-03-01 00:30 in Paris is stored as 2024-02-29 23:30+00, and bucketing it by the raw
# UTC value files it under February -- which is why client totals disagree with ours.
# Every month boundary below is therefore evaluated in the property's own timezone.
_LOCAL_CHECK_IN = "(r.check_in_date AT TIME ZONE p.timezone)"

_PROPERTY_JOIN = """
    FROM reservations r
    JOIN properties p
      ON p.id = r.property_id
     AND p.tenant_id = r.tenant_id
    WHERE r.property_id = :property_id
      AND r.tenant_id = :tenant_id
"""

_LATEST_PERIOD_SQL = text(f"""
    SELECT date_trunc('month', {_LOCAL_CHECK_IN}) AS period
    {_PROPERTY_JOIN}
    ORDER BY period DESC
    LIMIT 1
""")

_MONTHLY_REVENUE_SQL = text(f"""
    SELECT
        COALESCE(SUM(r.total_amount), 0) AS total_revenue,
        COUNT(*) AS reservation_count,
        COALESCE(MAX(r.currency), 'USD') AS currency
    {_PROPERTY_JOIN}
      AND {_LOCAL_CHECK_IN} >= :start_date
      AND {_LOCAL_CHECK_IN} < :end_date
""")


def _month_bounds(month: int, year: int) -> Tuple[datetime, datetime]:
    """Half-open [start, end) bounds for a month, as local wall-clock timestamps."""
    start_date = datetime(year, month, 1)
    if month < 12:
        end_date = datetime(year, month + 1, 1)
    else:
        end_date = datetime(year + 1, 1, 1)
    return start_date, end_date


async def _latest_period(session, property_id: str, tenant_id: str) -> Optional[Tuple[int, int]]:
    """Most recent month (in property-local time) that actually has reservations."""
    result = await session.execute(
        _LATEST_PERIOD_SQL,
        {"property_id": property_id, "tenant_id": tenant_id},
    )
    row = result.fetchone()
    if not row or row.period is None:
        return None
    return row.period.month, row.period.year


async def calculate_monthly_revenue(
    property_id: str,
    tenant_id: str,
    month: int,
    year: int,
    session,
) -> Dict[str, Any]:
    """Revenue for one property in one month, bucketed by the property's timezone."""
    start_date, end_date = _month_bounds(month, year)

    result = await session.execute(
        _MONTHLY_REVENUE_SQL,
        {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_date": start_date,
            "end_date": end_date,
        },
    )
    row = result.fetchone()

    return {
        # Kept as Decimal/str throughout: NUMERIC(10,3) does not survive a float round-trip.
        "total": Decimal(str(row.total_revenue)) if row else Decimal("0"),
        "count": row.reservation_count if row else 0,
        "currency": row.currency if row else "USD",
    }


async def calculate_total_revenue(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Aggregates revenue from database for a single month.

    When month/year are omitted, falls back to the latest month that has data for
    this property. Raises on database failure rather than substituting placeholder
    figures -- a silent fallback here reads as real revenue to the client.
    """
    await db_pool.initialize()

    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available")

    async with db_pool.get_session() as session:
        if month is None or year is None:
            period = await _latest_period(session, property_id, tenant_id)
            if period is None:
                # Property has no reservations at all.
                return {
                    "property_id": property_id,
                    "tenant_id": tenant_id,
                    "total": "0.00",
                    "currency": "USD",
                    "count": 0,
                    "period": None,
                }
            month, year = period

        revenue = await calculate_monthly_revenue(
            property_id, tenant_id, month, year, session
        )

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": str(revenue["total"]),
        "currency": revenue["currency"],
        "count": revenue["count"],
        "period": f"{year:04d}-{month:02d}",
    }
