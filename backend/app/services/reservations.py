from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database_pool import db_pool


class PropertyNotFoundError(Exception):
    pass


class MixedCurrencyError(Exception):
    pass


def _period_bounds(year: int, month: Optional[int], timezone_name: str):
    property_timezone = ZoneInfo(timezone_name)
    if month is None:
        start_local = datetime(year, 1, 1, tzinfo=property_timezone)
        end_local = datetime(year + 1, 1, 1, tzinfo=property_timezone)
    else:
        start_local = datetime(year, month, 1, tzinfo=property_timezone)
        if month == 12:
            end_local = datetime(year + 1, 1, 1, tzinfo=property_timezone)
        else:
            end_local = datetime(year, month + 1, 1, tzinfo=property_timezone)

    return (
        start_local.astimezone(timezone.utc),
        end_local.astimezone(timezone.utc),
    )


async def _get_property(
    session: AsyncSession, property_id: str, tenant_id: str
):
    result = await session.execute(
        text(
            """
            SELECT id, name, timezone
            FROM properties
            WHERE id = :property_id AND tenant_id = :tenant_id
            """
        ),
        {"property_id": property_id, "tenant_id": tenant_id},
    )
    property_row = result.fetchone()
    if not property_row:
        raise PropertyNotFoundError(property_id)
    return property_row

async def calculate_revenue(
    property_id: str,
    tenant_id: str,
    year: int,
    month: Optional[int] = None,
) -> Dict[str, Any]:
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        property_row = await _get_property(session, property_id, tenant_id)
        start_utc, end_utc = _period_bounds(year, month, property_row.timezone)
        result = await session.execute(
            text(
                """
                SELECT
                    COALESCE(currency, 'USD') AS currency,
                    SUM(total_amount) AS total_revenue,
                    COUNT(*) AS reservation_count
                FROM reservations
                WHERE property_id = :property_id
                    AND tenant_id = :tenant_id
                    AND check_in_date >= :start_utc
                    AND check_in_date < :end_utc
                GROUP BY COALESCE(currency, 'USD')
                """
            ),
            {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "start_utc": start_utc,
                "end_utc": end_utc,
            },
        )
        rows = result.fetchall()

    if len(rows) > 1:
        raise MixedCurrencyError(property_id)

    if rows:
        row = rows[0]
        total = Decimal(str(row.total_revenue or 0)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        currency = row.currency
        count = row.reservation_count
    else:
        total = Decimal("0.00")
        currency = "USD"
        count = 0

    return {
        "property_id": property_id,
        "property_name": property_row.name,
        "tenant_id": tenant_id,
        "year": year,
        "month": month,
        "timezone": property_row.timezone,
        "total": str(total),
        "currency": currency,
        "count": count,
    }


async def list_properties(
    tenant_id: str, page: int, page_size: int
) -> List[Dict[str, Any]]:
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        result = await session.execute(
            text(
                """
                SELECT id, name, timezone
                FROM properties
                WHERE tenant_id = :tenant_id
                ORDER BY id
                LIMIT :page_size OFFSET :offset
                """
            ),
            {
                "tenant_id": tenant_id,
                "page_size": page_size,
                "offset": (page - 1) * page_size,
            },
        )
        rows = result.fetchall()

    return [
        {"id": row.id, "name": row.name, "timezone": row.timezone}
        for row in rows
    ]
