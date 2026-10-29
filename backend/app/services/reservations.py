import logging
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

MONEY_QUANTUM = Decimal("0.01")
DEFAULT_REPORT_YEAR = 2024
DEFAULT_REPORT_MONTH = 3


def quantize_money(amount: Any) -> Decimal:
    return Decimal(str(amount)).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def format_money(amount: Any) -> str:
    return format(quantize_money(amount), "f")


def month_bounds(year: int, month: int, timezone_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(timezone_name or "UTC")
    start = datetime(year, month, 1, tzinfo=tz)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=tz)
    else:
        end = datetime(year, month + 1, 1, tzinfo=tz)
    return start, end


def revenue_cache_key(tenant_id: str, property_id: str, year: int, month: int) -> str:
    return f"revenue:{tenant_id}:{property_id}:{year}:{month:02d}"


async def calculate_monthly_revenue(
    property_id: str,
    month: int,
    year: int,
    tenant_id: str,
) -> Optional[Dict[str, Any]]:
    from sqlalchemy import text
    from app.core.database_pool import db_pool

    async with db_pool.get_session() as session:
        property_row = (
            await session.execute(
                text(
                    """
                    SELECT name, timezone
                    FROM properties
                    WHERE id = :property_id AND tenant_id = :tenant_id
                    """
                ),
                {"property_id": property_id, "tenant_id": tenant_id},
            )
        ).fetchone()

        if property_row is None:
            logger.info(
                "revenue property not in tenant property_id=%s tenant_id=%s",
                property_id,
                tenant_id,
            )
            return None

        start, end = month_bounds(year, month, property_row.timezone)
        logger.info(
            "revenue query property_id=%s tenant_id=%s tz=%s start=%s end=%s",
            property_id,
            tenant_id,
            property_row.timezone,
            start.isoformat(),
            end.isoformat(),
        )

        totals = (
            await session.execute(
                text(
                    """
                    SELECT
                        COALESCE(SUM(total_amount), 0) AS total_revenue,
                        COUNT(*) AS reservation_count,
                        COALESCE(MAX(currency), 'USD') AS currency
                    FROM reservations
                    WHERE property_id = :property_id
                      AND tenant_id = :tenant_id
                      AND check_in_date >= :start
                      AND check_in_date < :end
                    """
                ),
                {
                    "property_id": property_id,
                    "tenant_id": tenant_id,
                    "start": start,
                    "end": end,
                },
            )
        ).fetchone()

    return {
        "property_id": property_id,
        "property_name": property_row.name,
        "tenant_id": tenant_id,
        "timezone": property_row.timezone,
        "year": year,
        "month": month,
        "total": format_money(totals.total_revenue),
        "currency": totals.currency or "USD",
        "count": int(totals.reservation_count or 0),
    }


async def list_tenant_properties(tenant_id: str) -> list[Dict[str, str]]:
    from sqlalchemy import text
    from app.core.database_pool import db_pool

    async with db_pool.get_session() as session:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT id, name, timezone
                    FROM properties
                    WHERE tenant_id = :tenant_id
                    ORDER BY name
                    """
                ),
                {"tenant_id": tenant_id},
            )
        ).fetchall()

    return [{"id": row.id, "name": row.name, "timezone": row.timezone} for row in rows]