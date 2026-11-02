from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict
import pytz

from sqlalchemy import text


CENT = Decimal("0.01")


def _money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


async def calculate_monthly_revenue(
    property_id: str,
    month: int,
    year: int,
    tenant_id: str,
    db_session=None,
) -> Decimal:
    """Sum reservations whose check-in falls in the property's local month."""
    summary = await calculate_monthly_summary(
        property_id, month, year, tenant_id, db_session=db_session
    )
    return Decimal(summary["total"])


async def calculate_monthly_summary(
    property_id: str,
    month: int,
    year: int,
    tenant_id: str,
    db_session=None,
) -> Dict[str, Any]:
    """Return a tenant-scoped monthly revenue and reservation count."""
    if not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")

    from app.core.database_pool import db_pool

    if db_session is None:
        if db_pool.session_factory is None:
            await db_pool.initialize()
        session_context = await db_pool.get_session()
    else:
        session_context = None

    async def query(session):
        property_row = await session.execute(
            text("SELECT timezone FROM properties WHERE id = :property_id AND tenant_id = :tenant_id"),
            {"property_id": property_id, "tenant_id": tenant_id},
        )
        property_data = property_row.fetchone()
        if not property_data:
            return {"total": "0.00", "count": 0}

        timezone = pytz.timezone(property_data.timezone or "UTC")
        start_local = timezone.localize(datetime(year, month, 1), is_dst=None)
        if month == 12:
            end_local = timezone.localize(datetime(year + 1, 1, 1), is_dst=None)
        else:
            end_local = timezone.localize(datetime(year, month + 1, 1), is_dst=None)

        result = await session.execute(
            text("""
                SELECT COALESCE(SUM(total_amount), 0) AS total, COUNT(*) AS reservation_count
                FROM reservations
                WHERE property_id = :property_id AND tenant_id = :tenant_id
                  AND check_in_date >= :start_date AND check_in_date < :end_date
            """),
            {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "start_date": start_local,
                "end_date": end_local,
            },
        )
        row = result.fetchone()
        return {
            "total": format(_money(row.total), ".2f"),
            "count": row.reservation_count,
        }

    if db_session is not None:
        return await query(db_session)
    async with session_context as session:
        return await query(session)


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """Aggregate exact reservation amounts for one tenant's property."""
    from app.core.database_pool import db_pool

    if db_pool.session_factory is None:
        await db_pool.initialize()
    if db_pool.session_factory is None:
        raise RuntimeError("Database is unavailable")

    session_context = await db_pool.get_session()
    async with session_context as session:
        result = await session.execute(
            text("""
                SELECT COALESCE(SUM(total_amount), 0) AS total_revenue, COUNT(*) AS reservation_count
                FROM reservations
                WHERE property_id = :property_id AND tenant_id = :tenant_id
            """),
            {"property_id": property_id, "tenant_id": tenant_id},
        )
        row = result.fetchone()
        total = _money(row.total_revenue if row else 0)
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": format(total, ".2f"),
            "currency": "USD",
            "count": row.reservation_count if row else 0,
        }
