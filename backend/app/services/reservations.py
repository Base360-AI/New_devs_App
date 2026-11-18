from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text

from app.core.database_pool import db_pool


CENT = Decimal("0.01")


def month_bounds(month: str, timezone_name: str):
    year, month_number = (int(part) for part in month.split("-"))
    zone = ZoneInfo(timezone_name)
    start_local = datetime(year, month_number, 1, tzinfo=zone)
    if month_number == 12:
        next_local = datetime(year + 1, 1, 1, tzinfo=zone)
    else:
        next_local = datetime(year, month_number + 1, 1, tzinfo=zone)
    return start_local.astimezone(timezone.utc), next_local.astimezone(timezone.utc)


async def calculate_total_revenue(
    property_id: str, tenant_id: str, month: Optional[str] = None
) -> Dict[str, Any]:
    """Return property-local monthly revenue rounded to currency precision."""
    if not tenant_id:
        raise ValueError("Authenticated user has no tenant")
    if not db_pool.session_factory:
        await db_pool.initialize()

    async with db_pool.get_session() as session:
        property_row = (await session.execute(text("""
            SELECT timezone FROM properties
            WHERE id = :property_id AND tenant_id = :tenant_id
        """), {"property_id": property_id, "tenant_id": tenant_id})).first()
        if not property_row:
            return {"not_found": True}
        timezone_name = property_row.timezone or "UTC"
        zone = ZoneInfo(timezone_name)

        if month is None:
            latest = (await session.execute(text("""
                SELECT MAX(check_in_date) AS latest
                FROM reservations
                WHERE property_id = :property_id AND tenant_id = :tenant_id
            """), {"property_id": property_id, "tenant_id": tenant_id})).first()
            latest_date = latest.latest if latest else None
            month = latest_date.astimezone(zone).strftime("%Y-%m") if latest_date else datetime.now(zone).strftime("%Y-%m")

        try:
            start_utc, end_utc = month_bounds(month, timezone_name)
        except (ValueError, TypeError, ZoneInfoNotFoundError) as exc:
            raise ValueError("month must be YYYY-MM and timezone must be valid") from exc

        row = (await session.execute(text("""
            SELECT COALESCE(SUM(total_amount), 0) AS total,
                   COUNT(*) AS reservation_count,
                   COALESCE(MIN(currency), 'USD') AS currency
            FROM reservations
            WHERE property_id = :property_id AND tenant_id = :tenant_id
              AND check_in_date >= :start_utc AND check_in_date < :end_utc
        """), {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_utc": start_utc,
            "end_utc": end_utc,
        })).first()
        total = Decimal(str(row.total)).quantize(CENT, rounding=ROUND_HALF_UP)
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "month": month,
            "timezone": timezone_name,
            "total": format(total, ".2f"),
            "currency": row.currency,
            "count": row.reservation_count,
        }
