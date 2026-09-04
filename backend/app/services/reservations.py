from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database_pool import db_pool


DEFAULT_PROPERTY_TIMEZONE = "UTC"


def month_start(year: int, month: int, tz: ZoneInfo) -> datetime:
    return datetime(year, month, 1, tzinfo=tz)


def next_month_start(year: int, month: int, tz: ZoneInfo) -> datetime:
    if month < 12:
        return datetime(year, month + 1, 1, tzinfo=tz)
    return datetime(year + 1, 1, 1, tzinfo=tz)


def to_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


async def property_belongs_to_tenant(
    session: AsyncSession, property_id: str, tenant_id: str
) -> bool:
    query = text(
        """
        SELECT 1
        FROM properties
        WHERE id = :property_id AND tenant_id = :tenant_id
        """
    )
    result = await session.execute(
        query, {"property_id": property_id, "tenant_id": tenant_id}
    )
    return result.fetchone() is not None


async def list_tenant_properties(tenant_id: str) -> List[Dict[str, str]]:
    await db_pool.initialize()
    query = text(
        """
        SELECT id, name
        FROM properties
        WHERE tenant_id = :tenant_id
        ORDER BY name
        """
    )
    async with db_pool.get_session() as session:
        result = await session.execute(query, {"tenant_id": tenant_id})
        return [{"id": row.id, "name": row.name} for row in result.fetchall()]


async def tenant_owns_property(property_id: str, tenant_id: str) -> bool:
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        return await property_belongs_to_tenant(session, property_id, tenant_id)


async def fetch_property_timezone(
    session: AsyncSession, property_id: str, tenant_id: str
) -> str:
    query = text(
        """
        SELECT timezone
        FROM properties
        WHERE id = :property_id AND tenant_id = :tenant_id
        """
    )
    result = await session.execute(
        query, {"property_id": property_id, "tenant_id": tenant_id}
    )
    row = result.fetchone()
    if row and row.timezone:
        return row.timezone
    return DEFAULT_PROPERTY_TIMEZONE


async def fetch_latest_report_period(
    session: AsyncSession, property_id: str, tenant_id: str, tz: ZoneInfo
) -> Optional[Tuple[int, int]]:
    query = text(
        """
        SELECT check_in_date
        FROM reservations
        WHERE property_id = :property_id AND tenant_id = :tenant_id
        ORDER BY check_in_date DESC
        LIMIT 1
        """
    )
    result = await session.execute(
        query, {"property_id": property_id, "tenant_id": tenant_id}
    )
    row = result.fetchone()
    if not row or row.check_in_date is None:
        return None
    local_check_in = to_aware_utc(row.check_in_date).astimezone(tz)
    return local_check_in.year, local_check_in.month


async def sum_revenue_in_range(
    session: AsyncSession,
    property_id: str,
    tenant_id: str,
    start_date: datetime,
    end_date: datetime,
) -> Tuple[Decimal, int]:
    query = text(
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
    )
    result = await session.execute(
        query,
        {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_date": start_date,
            "end_date": end_date,
        },
    )
    row = result.fetchone()
    total = Decimal(str(row.total_revenue)) if row else Decimal("0")
    count = int(row.reservation_count) if row else 0
    return total, count


async def calculate_monthly_revenue(
    property_id: str,
    month: int,
    year: int,
    tenant_id: str,
    db_session: Optional[AsyncSession] = None,
) -> Decimal:
    """
    Calculates revenue for a calendar month in the property's local timezone.
    """
    total, _count = await calculate_monthly_revenue_with_count(
        property_id, month, year, tenant_id, db_session
    )
    return total


async def calculate_monthly_revenue_with_count(
    property_id: str,
    month: int,
    year: int,
    tenant_id: str,
    db_session: Optional[AsyncSession] = None,
) -> Tuple[Decimal, int]:
    async def run(session: AsyncSession) -> Tuple[Decimal, int]:
        timezone_name = await fetch_property_timezone(session, property_id, tenant_id)
        tz = ZoneInfo(timezone_name)
        start_date = month_start(year, month, tz)
        end_date = next_month_start(year, month, tz)
        return await sum_revenue_in_range(
            session, property_id, tenant_id, start_date, end_date
        )

    if db_session is not None:
        return await run(db_session)

    await db_pool.initialize()
    async with db_pool.get_session() as session:
        return await run(session)


def empty_revenue_result(property_id: str, tenant_id: str) -> Dict[str, Any]:
    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": "0.00",
        "currency": "USD",
        "count": 0,
    }


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates monthly revenue using the property timezone (not UTC).
    The reported month is the latest check-in month in that timezone.
    """
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        timezone_name = await fetch_property_timezone(session, property_id, tenant_id)
        tz = ZoneInfo(timezone_name)
        period = await fetch_latest_report_period(session, property_id, tenant_id, tz)
        if period is None:
            return empty_revenue_result(property_id, tenant_id)

        year, month = period
        total_revenue, reservation_count = await calculate_monthly_revenue_with_count(
            property_id, month, year, tenant_id, session
        )
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": str(total_revenue),
            "currency": "USD",
            "count": reservation_count,
        }
