import asyncio
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional

import asyncpg

from app.config import settings

_pool = None
_pool_lock = asyncio.Lock()


async def get_pool():
    global _pool
    if _pool is None:
        async with _pool_lock:
            if _pool is None:
                _pool = await asyncpg.create_pool(dsn=settings.database_url)
    return _pool


async def calculate_monthly_revenue(
    property_id: str, month: int, year: int, tenant_id: str
) -> Decimal:
    """Return the month's revenue using the property's local check-in date."""
    summary = await calculate_total_revenue(property_id, tenant_id, month, year)
    return Decimal(summary["total"])


async def calculate_total_revenue(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> Dict[str, Any]:
    """Summarize reservations for a property owned by the authenticated tenant."""
    pool = await get_pool()
    async with pool.acquire() as connection:
        property_result = await connection.fetchrow(
            "SELECT id FROM properties WHERE id = $1 AND tenant_id = $2",
            property_id, tenant_id,
        )
        if property_result is None:
            raise LookupError("Property not found")

        date_filter = ""
        params = [property_id, tenant_id]
        if month is not None and year is not None:
            start_date = datetime(year, month, 1)
            end_date = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
            date_filter = """
                AND (r.check_in_date AT TIME ZONE p.timezone) >= $3
                AND (r.check_in_date AT TIME ZONE p.timezone) < $4
            """
            params.extend([start_date, end_date])

        rows = await connection.fetch(
            f"""
                SELECT r.currency, COALESCE(SUM(r.total_amount), 0) AS total,
                       COUNT(*) AS reservation_count
                FROM reservations r
                JOIN properties p ON p.id = r.property_id AND p.tenant_id = r.tenant_id
                WHERE r.property_id = $1 AND r.tenant_id = $2
                {date_filter}
                GROUP BY r.currency
            """,
            *params,
        )

    if len(rows) > 1:
        raise ValueError("Property reservations contain multiple currencies")

    total = rows[0]["total"] if rows else Decimal("0")
    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": str(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        "currency": rows[0]["currency"] if rows else "USD",
        "count": rows[0]["reservation_count"] if rows else 0,
    }
