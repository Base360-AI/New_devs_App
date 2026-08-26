from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List


class PropertyNotFoundError(Exception):
    """Raised when a property is not available to the current tenant."""


class MixedCurrencyError(Exception):
    """Raised when a monthly summary would combine multiple currencies."""


def _month_bounds(month: int, year: int) -> tuple[datetime, datetime]:
    month_start = datetime(year, month, 1)
    if month == 12:
        month_end = datetime(year + 1, 1, 1)
    else:
        month_end = datetime(year, month + 1, 1)
    return month_start, month_end


async def calculate_monthly_revenue(
    property_id: str,
    tenant_id: str,
    month: int,
    year: int,
) -> Dict[str, Any]:
    """Calculate one property's revenue using its local calendar month."""
    from sqlalchemy import text

    from app.core.database_pool import db_pool

    month_start, month_end = _month_bounds(month, year)
    await db_pool.initialize()

    async with db_pool.get_session() as session:
        query = text(
            """
            SELECT
                p.id AS property_id,
                COALESCE(ROUND(SUM(r.total_amount), 2), 0.00) AS total_revenue,
                COUNT(r.id) AS reservation_count,
                COALESCE(MIN(r.currency), 'USD') AS currency,
                COUNT(DISTINCT r.currency) AS currency_count
            FROM properties p
            LEFT JOIN reservations r
                ON r.property_id = p.id
                AND r.tenant_id = p.tenant_id
                AND (r.check_in_date AT TIME ZONE p.timezone) >= :month_start
                AND (r.check_in_date AT TIME ZONE p.timezone) < :month_end
            WHERE p.id = :property_id
                AND p.tenant_id = :tenant_id
            GROUP BY p.id
            """
        )
        result = await session.execute(
            query,
            {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "month_start": month_start,
                "month_end": month_end,
            },
        )
        row = result.fetchone()

    if not row:
        raise PropertyNotFoundError(property_id)
    if row.currency_count > 1:
        raise MixedCurrencyError(
            f"Multiple currencies found for property {property_id}"
        )

    total_revenue = Decimal(str(row.total_revenue))
    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "month": month,
        "year": year,
        "total": format(total_revenue, ".2f"),
        "currency": row.currency,
        "count": row.reservation_count,
    }


async def get_tenant_properties(tenant_id: str) -> List[Dict[str, str]]:
    """Return the properties visible to a tenant."""
    from sqlalchemy import text

    from app.core.database_pool import db_pool

    await db_pool.initialize()
    async with db_pool.get_session() as session:
        result = await session.execute(
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
        rows = result.fetchall()

    return [
        {"id": row.id, "name": row.name, "timezone": row.timezone}
        for row in rows
    ]
