import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class RevenueDataUnavailable(RuntimeError):
    """
    Raised when revenue cannot be read from the database.

    Callers must surface this as an error. Returning a plausible-looking
    number in its place is what hid the broken connection pool for so long.
    """


async def _fetch_revenue_row(query, params: Dict[str, Any], context: str):
    """
    Runs a revenue aggregate and returns its single row.
    """
    from app.core.database_pool import db_pool

    try:
        await db_pool.initialize()
        async with db_pool.get_session() as session:
            result = await session.execute(query, params)
            return result.fetchone()
    except Exception as e:
        logger.error(f"Database error for {context}: {e}")
        raise RevenueDataUnavailable(f"Could not read revenue for {context}") from e


def _month_bounds(month: int, year: int):
    """
    Returns the half-open [start, end) local month boundaries.
    """
    if not 1 <= month <= 12:
        raise ValueError(f"month must be between 1 and 12, got {month}")

    start_date = datetime(year, month, 1)
    if month < 12:
        end_date = datetime(year, month + 1, 1)
    else:
        end_date = datetime(year + 1, 1, 1)
    return start_date, end_date


async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Dict[str, Any]:
    """
    Calculates revenue for a specific month, in the property's own timezone.

    A booking belongs to the month the guest checked in locally, which is what
    the merchant reconciles against. check_in_date is TIMESTAMPTZ, so comparing
    it to naive UTC boundaries misfiles any check-in that falls on either side
    of local midnight: a 2024-02-29 23:30Z arrival is 1 March in Europe/Paris.
    Converting with AT TIME ZONE p.timezone uses the zone the schema already
    records per property.
    """
    from sqlalchemy import text

    start_date, end_date = _month_bounds(month, year)

    query = text("""
        SELECT
            COALESCE(SUM(r.total_amount), 0) as total_revenue,
            COUNT(*) as reservation_count
        FROM reservations r
        JOIN properties p
            ON p.id = r.property_id AND p.tenant_id = r.tenant_id
        WHERE r.property_id = :property_id
            AND r.tenant_id = :tenant_id
            AND (r.check_in_date AT TIME ZONE p.timezone) >= :start_date
            AND (r.check_in_date AT TIME ZONE p.timezone) < :end_date
    """)

    row = await _fetch_revenue_row(
        query,
        {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_date": start_date,
            "end_date": end_date,
        },
        f"{property_id} (tenant: {tenant_id}, {year}-{month:02d})",
    )

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": str(Decimal(str(row.total_revenue))),
        "currency": "USD",
        "count": row.reservation_count,
        "month": month,
        "year": year,
    }


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    from sqlalchemy import text

    query = text("""
        SELECT
            COALESCE(SUM(total_amount), 0) as total_revenue,
            COUNT(*) as reservation_count
        FROM reservations
        WHERE property_id = :property_id AND tenant_id = :tenant_id
    """)

    row = await _fetch_revenue_row(
        query,
        {"property_id": property_id, "tenant_id": tenant_id},
        f"{property_id} (tenant: {tenant_id})",
    )

    # An aggregate without GROUP BY always returns exactly one row, so a
    # property with no reservations reports 0.00 rather than falling through
    # to a branch that could invent a figure.
    total_revenue = Decimal(str(row.total_revenue))

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": str(total_revenue),
        "currency": "USD",
        "count": row.reservation_count
    }
