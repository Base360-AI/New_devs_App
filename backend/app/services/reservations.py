from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, Optional
from app.core.database_pool import db_pool


CENT = Decimal("0.01")


async def _fetch_revenue_row(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
    db_session=None,
):
    if not tenant_id:
        raise ValueError("A tenant_id is required to calculate revenue")
    if (month is None) != (year is None):
        raise ValueError("Both month and year are required for monthly revenue")

    date_filter = ""
    params: Dict[str, Any] = {
        "property_id": property_id,
        "tenant_id": tenant_id,
    }
    if month is not None and year is not None:
        start_date = datetime(year, month, 1)
        end_date = (
            datetime(year + 1, 1, 1)
            if month == 12
            else datetime(year, month + 1, 1)
        )
        date_filter = """
          AND timezone(p.timezone, r.check_in_date) >= :start_date
          AND timezone(p.timezone, r.check_in_date) < :end_date
        """
        params.update(start_date=start_date, end_date=end_date)

    from sqlalchemy import text

    query = text("""
        SELECT
            SUM(r.total_amount) AS total_revenue,
            COUNT(r.id) AS reservation_count,
            COUNT(DISTINCT r.currency) AS currency_count,
            MIN(r.currency) AS currency
        FROM reservations AS r
        JOIN properties AS p
          ON p.id = r.property_id
         AND p.tenant_id = r.tenant_id
        WHERE r.property_id = :property_id
          AND r.tenant_id = :tenant_id
    """ + date_filter)
    await db_pool.initialize()
    if db_session is not None:
        result = await db_session.execute(query, params)
        return result.fetchone()

    async with db_pool.get_session() as session:
        result = await session.execute(query, params)
        return result.fetchone()


def _rounded_total(value: Optional[Decimal]) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


async def calculate_monthly_revenue(
    property_id: str,
    month: int,
    year: int,
    db_session=None,
    tenant_id: Optional[str] = None,
) -> Decimal:
    """Calculates revenue for a property-local calendar month."""
    row = await _fetch_revenue_row(
        property_id,
        tenant_id,
        month=month,
        year=year,
        db_session=db_session,
    )
    return _rounded_total(row.total_revenue if row else None)


async def calculate_total_revenue(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Aggregates revenue for a property and tenant, optionally for a local month.
    """
    row = await _fetch_revenue_row(property_id, tenant_id, month=month, year=year)
    if row and row.currency_count > 1:
        raise ValueError(
            f"Property {property_id} has reservations in multiple currencies; "
            "revenue cannot be combined without an exchange rate"
        )

    total_revenue = _rounded_total(row.total_revenue if row else None)
    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": f"{total_revenue:.2f}",
        "currency": row.currency if row and row.currency else "USD",
        "count": row.reservation_count if row else 0,
    }
