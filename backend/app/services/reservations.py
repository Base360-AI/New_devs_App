from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import text

from app.core.database_pool import db_pool


def monthly_utc_bounds(month: int, year: int, property_timezone: str):
    """Use local calendar boundaries, including DST, then query in UTC."""
    zone = ZoneInfo(property_timezone)
    start = datetime(year, month, 1, tzinfo=zone)
    end = datetime(year + 1, 1, 1, tzinfo=zone) if month == 12 else datetime(
        year, month + 1, 1, tzinfo=zone
    )
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


async def list_revenue_properties(tenant_id: str):
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        result = await session.execute(
            text("SELECT id, name FROM properties WHERE tenant_id = :tenant_id ORDER BY id"),
            {"tenant_id": tenant_id},
        )
        return [dict(row) for row in result.mappings()]


async def calculate_monthly_revenue(
    property_id: str, tenant_id: str, month: int, year: int
) -> Dict[str, Any]:
    """Sum exact amounts for check-ins in the property's local calendar month."""
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        result = await session.execute(
            text("SELECT timezone FROM properties WHERE id = :property_id AND tenant_id = :tenant_id"),
            {"property_id": property_id, "tenant_id": tenant_id},
        )
        property_timezone = result.scalar_one_or_none()
        if property_timezone is None:
            raise HTTPException(status_code=404, detail="Property not found")

        start, end = monthly_utc_bounds(month, year, property_timezone)
        result = await session.execute(
            text("""
                SELECT currency, SUM(total_amount) AS total, COUNT(*) AS count
                FROM reservations
                WHERE property_id = :property_id AND tenant_id = :tenant_id
                  AND check_in_date >= :start AND check_in_date < :end
                GROUP BY currency
            """),
            {"property_id": property_id, "tenant_id": tenant_id, "start": start, "end": end},
        )
        rows = result.mappings().all()
        if len(rows) > 1:
            raise HTTPException(status_code=422, detail="Cannot combine revenue in different currencies")
        row = rows[0] if rows else None
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "month": month,
            "year": year,
            "total": str(row["total"] if row else Decimal("0.00")),
            "currency": row["currency"] if row else "USD",
            "count": row["count"] if row else 0,
        }
