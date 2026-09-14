from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import text

from app.core.database_pool import db_pool


def revenue_period(year: int, month: int | None, property_timezone: str):
    """Half-open reporting period: property-local calendar boundaries in UTC."""
    tz = ZoneInfo(property_timezone)
    start = datetime(year, month or 1, 1, tzinfo=tz)
    if month is None or month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=tz)
    else:
        end = datetime(year, month + 1, 1, tzinfo=tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


async def calculate_total_revenue(
    property_id: str, tenant_id: str, year: int, month: int | None
) -> dict:
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        property_row = (await session.execute(text("""
            SELECT timezone FROM properties
            WHERE id = :property_id AND tenant_id = :tenant_id
        """), {"property_id": property_id, "tenant_id": tenant_id})).first()
        if property_row is None:
            raise HTTPException(status_code=404, detail="Property not found")

        start, end = revenue_period(year, month, property_row.timezone)
        rows = (await session.execute(text("""
            SELECT currency, SUM(total_amount) AS total, COUNT(*) AS count
            FROM reservations
            WHERE property_id = :property_id AND tenant_id = :tenant_id
              AND check_in_date >= :start AND check_in_date < :end
            GROUP BY currency ORDER BY currency
        """), {
            "property_id": property_id, "tenant_id": tenant_id,
            "start": start, "end": end,
        })).all()

    return {
        "property_id": property_id, "tenant_id": tenant_id,
        "year": year, "month": month, "timezone": property_row.timezone,
        "total": str(sum((row.total for row in rows), Decimal("0"))),
        "currency": "USD",
        "count": sum(row.count for row in rows),
    }
