"""
Revenue calculations for property reservations.

Money rules (see FINDINGS.md):
  * Amounts are stored as NUMERIC(10, 3) and are summed in the database (exact).
  * Rounding to cents happens exactly once, on the final total, with ROUND_HALF_UP.
  * Amounts are never converted to float on the backend; the API serialises them as strings.

Time rules:
  * check_in_date is TIMESTAMPTZ. A "month" is defined in the *property's* local timezone
    (properties.timezone), because that is how the client's own books define it.
"""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, Optional, List, Tuple
import logging

from sqlalchemy import text

from app.core.database_pool import db_pool

logger = logging.getLogger(__name__)

CENT = Decimal("0.01")


def to_money(amount: Decimal) -> Decimal:
    """Round a Decimal amount to cents, half-up (financial rounding)."""
    return Decimal(amount).quantize(CENT, rounding=ROUND_HALF_UP)


def month_bounds(year: int, month: int) -> Tuple[datetime, datetime]:
    """Half-open [start, end) wall-clock bounds of a calendar month (naive datetimes).

    These are compared against `check_in_date AT TIME ZONE properties.timezone`, i.e.
    the reservation's local wall-clock time, so a booking at 2024-02-29 23:30 UTC for a
    Paris property (= 2024-03-01 00:30 local) correctly lands in March.
    """
    if not 1 <= month <= 12:
        raise ValueError(f"month must be 1..12, got {month}")
    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    return start, end


async def calculate_revenue(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Sum reservation revenue for one property of one tenant.

    If month/year are given, only reservations whose check-in falls within that calendar
    month *in the property's timezone* are counted; otherwise all reservations.

    Returns None if the property does not exist for this tenant. Raises on database
    errors - callers must NOT mask failures with fabricated numbers.
    """
    if (month is None) != (year is None):
        raise ValueError("month and year must be provided together")

    await db_pool.initialize()

    params: Dict[str, Any] = {"property_id": property_id, "tenant_id": tenant_id}
    period_filter = ""
    if month is not None:
        start, end = month_bounds(year, month)
        params["start"] = start
        params["end"] = end
        # AT TIME ZONE converts the TIMESTAMPTZ to the property's local wall-clock time.
        period_filter = """
            AND (r.check_in_date AT TIME ZONE p.timezone) >= :start
            AND (r.check_in_date AT TIME ZONE p.timezone) <  :end
        """

    query = text(f"""
        SELECT
            p.id                              AS property_id,
            p.name                            AS property_name,
            p.timezone                        AS timezone,
            COALESCE(SUM(r.total_amount), 0)  AS total_revenue,
            COUNT(r.id)                       AS reservation_count
        FROM properties p
        LEFT JOIN reservations r
               ON r.property_id = p.id
              AND r.tenant_id   = p.tenant_id
              {period_filter}
        WHERE p.id = :property_id
          AND p.tenant_id = :tenant_id
        GROUP BY p.id, p.name, p.timezone
    """)

    async with db_pool.get_session() as session:
        result = await session.execute(query, params)
        row = result.fetchone()

    if row is None:
        return None

    total = to_money(Decimal(str(row.total_revenue)))
    return {
        "property_id": row.property_id,
        "property_name": row.property_name,
        "tenant_id": tenant_id,
        "timezone": row.timezone,
        "total": str(total),
        "currency": "USD",
        "count": int(row.reservation_count),
        "month": month,
        "year": year,
    }


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    """All-time revenue for a property. Kept for backwards compatibility."""
    return await calculate_revenue(property_id, tenant_id)


async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Optional[Dict[str, Any]]:
    """Revenue for a calendar month in the property's local timezone."""
    return await calculate_revenue(property_id, tenant_id, month=month, year=year)


async def list_properties(tenant_id: str) -> List[Dict[str, Any]]:
    """Properties visible to a tenant (never leaks other tenants' properties)."""
    await db_pool.initialize()
    query = text("""
        SELECT id, name, timezone
        FROM properties
        WHERE tenant_id = :tenant_id
        ORDER BY id
    """)
    async with db_pool.get_session() as session:
        result = await session.execute(query, {"tenant_id": tenant_id})
        rows = result.fetchall()
    return [{"id": r.id, "name": r.name, "timezone": r.timezone} for r in rows]
