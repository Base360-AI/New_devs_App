from decimal import Decimal
from typing import Dict, Any, Optional

from sqlalchemy import text


def _format_decimal(value: Decimal) -> str:
    return format(value, "f")

async def calculate_monthly_revenue(
    property_id: str,
    tenant_id: str,
    month: int,
    year: int,
) -> Decimal:
    result = await calculate_total_revenue(
        property_id=property_id,
        tenant_id=tenant_id,
        month=month,
        year=year,
    )
    return Decimal(result["total_revenue"])

async def calculate_total_revenue(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    from app.core.database_pool import db_pool

    if month is not None and (month < 1 or month > 12):
        raise ValueError("month must be between 1 and 12")
    if (month is None) != (year is None):
        raise ValueError("month and year must be provided together")

    if db_pool.session_factory is None:
        await db_pool.initialize()

    if db_pool.session_factory is None:
        raise RuntimeError("Database pool not available")

    base_query = """
        SELECT
            r.property_id,
            COALESCE(SUM(r.total_amount), 0) AS total_revenue,
            COUNT(*) AS reservation_count,
            COALESCE(MIN(r.currency), 'USD') AS currency
        FROM reservations r
        INNER JOIN properties p
            ON p.id = r.property_id
           AND p.tenant_id = r.tenant_id
        WHERE r.property_id = :property_id
          AND r.tenant_id = :tenant_id
    """

    params: Dict[str, Any] = {
        "property_id": property_id,
        "tenant_id": tenant_id,
    }

    if month is not None and year is not None:
        query = text(
            base_query
            + """
          AND EXTRACT(MONTH FROM timezone(p.timezone, r.check_in_date)) = :month
          AND EXTRACT(YEAR FROM timezone(p.timezone, r.check_in_date)) = :year
        GROUP BY r.property_id
        """
        )
        params["month"] = month
        params["year"] = year
    else:
        query = text(
            base_query
            + """
        GROUP BY r.property_id
        """
        )

    async with db_pool.get_session() as session:
        result = await session.execute(query, params)
        row = result.fetchone()

    if row:
        total_revenue = Decimal(str(row.total_revenue))
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total_revenue": _format_decimal(total_revenue),
            "currency": row.currency,
            "reservations_count": int(row.reservation_count),
            "month": month,
            "year": year,
        }

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total_revenue": "0.00",
        "currency": "USD",
        "reservations_count": 0,
        "month": month,
        "year": year,
    }
