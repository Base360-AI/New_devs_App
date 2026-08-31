from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

MONEY_QUANTUM = Decimal("0.01")


def _month_boundaries_utc(year: int, month: int, timezone_name: str):
    """Return the half-open local month boundaries converted to UTC."""
    try:
        property_timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Invalid property timezone: {timezone_name}") from exc

    start_local = datetime(year, month, 1, tzinfo=property_timezone)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, tzinfo=property_timezone)
    else:
        end_local = datetime(year, month + 1, 1, tzinfo=property_timezone)

    return (
        start_local.astimezone(timezone.utc),
        end_local.astimezone(timezone.utc),
    )


async def _calculate_monthly_revenue_summary(
    property_id: str,
    tenant_id: str,
    month: int,
    year: int,
    db_session: AsyncSession,
) -> Dict[str, Any]:
    property_result = await db_session.execute(
        text("""
            SELECT timezone
            FROM properties
            WHERE id = :property_id AND tenant_id = :tenant_id
        """),
        {"property_id": property_id, "tenant_id": tenant_id},
    )
    property_row = property_result.fetchone()
    if not property_row:
        raise ValueError(
            f"Property {property_id} was not found for tenant {tenant_id}"
        )

    start_utc, end_utc = _month_boundaries_utc(
        year,
        month,
        property_row.timezone,
    )

    revenue_result = await db_session.execute(
        text("""
            SELECT
                COALESCE(SUM(total_amount), 0) AS total_revenue,
                COUNT(*) AS reservation_count,
                COALESCE(MIN(currency), :default_currency) AS currency
            FROM reservations
            WHERE property_id = :property_id
              AND tenant_id = :tenant_id
              AND check_in_date >= :start_utc
              AND check_in_date < :end_utc
        """),
        {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_utc": start_utc,
            "end_utc": end_utc,
            "default_currency": "USD",
        },
    )
    row = revenue_result.fetchone()
    total_revenue = Decimal(str(row.total_revenue))
    rounded_total = total_revenue.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "month": month,
        "year": year,
        "total": format(rounded_total, ".2f"),
        "currency": row.currency,
        "count": row.reservation_count,
    }


async def calculate_monthly_revenue(
    property_id: str,
    tenant_id: str,
    month: int,
    year: int,
    db_session: AsyncSession | None = None,
) -> Decimal:
    """Calculate exact revenue for a property month in its local timezone."""
    summary = await calculate_monthly_revenue_summary(
        property_id,
        tenant_id,
        month,
        year,
        db_session,
    )
    return Decimal(summary["total"])


async def calculate_monthly_revenue_summary(
    property_id: str,
    tenant_id: str,
    month: int,
    year: int,
    db_session: AsyncSession | None = None,
) -> Dict[str, Any]:
    """Calculate a dashboard-ready monthly revenue summary."""
    if db_session is not None:
        return await _calculate_monthly_revenue_summary(
            property_id,
            tenant_id,
            month,
            year,
            db_session,
        )

    from app.core.database_pool import db_pool

    if not db_pool.session_factory:
        await db_pool.initialize()
    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available")

    async with db_pool.get_session() as session:
        return await _calculate_monthly_revenue_summary(
            property_id,
            tenant_id,
            month,
            year,
            session,
        )
