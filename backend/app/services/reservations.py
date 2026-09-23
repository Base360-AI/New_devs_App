from datetime import datetime
from decimal import Decimal
from typing import Any, Dict

from fastapi import HTTPException
from sqlalchemy import text

from app.core.database_pool import db_pool


async def calculate_monthly_revenue(
    property_id: str, tenant_id: str, month: int = 3, year: int = 2024
) -> Dict[str, Any]:
    """Sum exact amounts in the property's local calendar month, per currency."""
    start = datetime(year, month, 1)
    end = datetime(year + (month == 12), 1 if month == 12 else month + 1, 1)
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        result = await session.execute(text("""
            SELECT timezone FROM properties
            WHERE id = :property_id AND tenant_id = :tenant_id
        """), {"property_id": property_id, "tenant_id": tenant_id})
        prop = result.fetchone()
        if prop is None:
            raise HTTPException(status_code=404, detail="Property not found")

        result = await session.execute(text("""
            SELECT currency, SUM(total_amount) AS total_revenue,
                   COUNT(*) AS reservation_count
            FROM reservations
            WHERE property_id = :property_id AND tenant_id = :tenant_id
              AND check_in_date >= (CAST(:start AS timestamp) AT TIME ZONE :timezone)
              AND check_in_date < (CAST(:end AS timestamp) AT TIME ZONE :timezone)
            GROUP BY currency ORDER BY currency
        """), {
            "property_id": property_id, "tenant_id": tenant_id,
            "start": start, "end": end, "timezone": prop.timezone,
        })
        totals = [{
            "currency": row.currency or "Unknown",
            "total": str(Decimal(str(row.total_revenue))),
            "count": row.reservation_count,
        } for row in result.fetchall()]
        return {
            "property_id": property_id, "tenant_id": tenant_id,
            "month": month, "year": year, "totals": totals,
            "total": totals[0]["total"] if len(totals) == 1 else ("0.000" if not totals else None),
            "currency": totals[0]["currency"] if len(totals) == 1 else None,
            "count": sum(item["count"] for item in totals),
        }


async def calculate_total_revenue(
    property_id: str, tenant_id: str, month: int = 3, year: int = 2024
) -> Dict[str, Any]:
    return await calculate_monthly_revenue(property_id, tenant_id, month, year)
