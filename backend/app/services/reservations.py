from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.core.database_pool import db_pool


class PropertyNotFoundError(Exception):
    """The property does not exist for this tenant"""


class MixedCurrencyError(Exception):
    """Reservations of one property use more than one currency"""


def get_local_period(timezone: str, year: int, month: Optional[int] = None) -> Tuple[datetime, datetime]:
    """
    Returns the start (inclusive) and end (exclusive) of a month or a year
    in the property's local time zone, so bookings are counted in the
    month they happened for the property, not in UTC.
    """
    tz = ZoneInfo(timezone)

    if month is None:
        return datetime(year, 1, 1, tzinfo=tz), datetime(year + 1, 1, 1, tzinfo=tz)

    start_date = datetime(year, month, 1, tzinfo=tz)
    if month < 12:
        end_date = datetime(year, month + 1, 1, tzinfo=tz)
    else:
        end_date = datetime(year + 1, 1, 1, tzinfo=tz)
    return start_date, end_date


async def get_tenant_properties(tenant_id: str) -> List[Dict[str, Any]]:
    """
    Lists the properties that belong to a tenant.
    """
    async with db_pool.tenant_session(tenant_id) as session:
        query = text("""
            SELECT id, name, timezone
            FROM properties
            WHERE tenant_id = :tenant_id
            ORDER BY id
        """)
        result = await session.execute(query, {"tenant_id": tenant_id})
        return [
            {"id": row.id, "name": row.name, "timezone": row.timezone}
            for row in result
        ]


async def get_tenant_property(property_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    """
    Returns a property if it belongs to the tenant, otherwise None.
    """
    async with db_pool.tenant_session(tenant_id) as session:
        return await _fetch_property(session, property_id, tenant_id)


async def _fetch_property(session, property_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    query = text("""
        SELECT id, name, timezone
        FROM properties
        WHERE id = :property_id AND tenant_id = :tenant_id
    """)
    result = await session.execute(query, {"property_id": property_id, "tenant_id": tenant_id})
    row = result.fetchone()
    if not row:
        return None
    return {"id": row.id, "name": row.name, "timezone": row.timezone}


async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Dict[str, Any]:
    """
    Calculates revenue for a specific month in the property's local time zone.
    """
    return await calculate_total_revenue(property_id, tenant_id, year=year, month=month)


async def calculate_total_revenue(
    property_id: str,
    tenant_id: str,
    year: Optional[int] = None,
    month: Optional[int] = None
) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    Without a year it covers all reservations; with a year (and optionally a month)
    it covers that period in the property's local time zone, by check-in date.
    """
    if month is not None and year is None:
        raise ValueError("month requires year")

    async with db_pool.tenant_session(tenant_id) as session:
        property_row = await _fetch_property(session, property_id, tenant_id)
        if not property_row:
            raise PropertyNotFoundError(property_id)

        params: Dict[str, Any] = {"property_id": property_id, "tenant_id": tenant_id}
        period_filter = ""
        if year is not None:
            params["start_date"], params["end_date"] = get_local_period(property_row["timezone"], year, month)
            period_filter = "AND check_in_date >= :start_date AND check_in_date < :end_date"

        query = text(f"""
            SELECT
                currency,
                SUM(total_amount) as total_revenue,
                COUNT(*) as reservation_count
            FROM reservations
            WHERE property_id = :property_id AND tenant_id = :tenant_id
            {period_filter}
            GROUP BY currency
        """)

        result = await session.execute(query, params)
        rows = result.fetchall()

    if len(rows) > 1:
        currencies = sorted(str(row.currency) for row in rows)
        raise MixedCurrencyError(f"Property {property_id} has reservations in {', '.join(currencies)}")

    row = rows[0] if rows else None
    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "timezone": property_row["timezone"],
        "year": year,
        "month": month,
        "total": str(row.total_revenue) if row else "0",
        # No reservations means there is no currency to report
        "currency": row.currency if row else None,
        "count": row.reservation_count if row else 0
    }
