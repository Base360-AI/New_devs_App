from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple

import pytz
from sqlalchemy import text

from app.core.database_pool import db_pool


class PropertyNotFound(Exception):
    """Raised when a property does not exist for the requesting tenant."""


async def _get_property_timezone(session, property_id: str, tenant_id: str) -> str:
    """Return the property's IANA timezone.

    Doubles as the tenant ownership check: properties are keyed by
    (id, tenant_id), so a miss means the property does not belong to the
    caller's tenant and must not be reported on.
    """
    result = await session.execute(
        text("""
            SELECT timezone
            FROM properties
            WHERE id = :property_id AND tenant_id = :tenant_id
        """),
        {"property_id": property_id, "tenant_id": tenant_id},
    )
    row = result.fetchone()
    if not row:
        raise PropertyNotFound(f"Property {property_id} not found for tenant {tenant_id}")
    return row.timezone or "UTC"


def month_bounds_utc(month: int, year: int, property_timezone: str) -> Tuple[datetime, datetime]:
    """Return the UTC instants bounding a calendar month in the property's local time.

    A "March" total means March *where the property is*. Building the bounds as
    naive UTC datetimes silently shifts every property's month by its UTC offset,
    which is what made a 2024-02-29 23:30Z check-in (00:30 on 1 March in Paris)
    fall outside Sunset Properties' March figures.
    """
    tz = pytz.timezone(property_timezone)

    local_start = tz.localize(datetime(year, month, 1))
    if month < 12:
        local_end = tz.localize(datetime(year, month + 1, 1))
    else:
        local_end = tz.localize(datetime(year + 1, 1, 1))

    return local_start.astimezone(pytz.UTC), local_end.astimezone(pytz.UTC)


async def _aggregate_revenue(
    session,
    property_id: str,
    tenant_id: str,
    start_utc: Optional[datetime] = None,
    end_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Sum reservation amounts for one property, always scoped to one tenant.

    Aggregation stays in NUMERIC on the database side and is carried into
    Python as Decimal — never float — so sub-cent amounts add up exactly.
    """
    query = """
        SELECT
            SUM(total_amount) AS total_revenue,
            COUNT(*) AS reservation_count,
            COUNT(DISTINCT currency) AS currency_count,
            MIN(currency) AS currency
        FROM reservations
        WHERE property_id = :property_id
          AND tenant_id = :tenant_id
    """
    params: Dict[str, Any] = {"property_id": property_id, "tenant_id": tenant_id}

    if start_utc is not None and end_utc is not None:
        query += " AND check_in_date >= :start_date AND check_in_date < :end_date"
        params["start_date"] = start_utc
        params["end_date"] = end_utc

    result = await session.execute(text(query), params)
    row = result.fetchone()

    count = row.reservation_count if row else 0
    if not count:
        return {"total": Decimal("0"), "count": 0, "currency": "USD"}

    if row.currency_count > 1:
        raise ValueError(
            f"Property {property_id} has reservations in multiple currencies; "
            "totals cannot be summed without conversion rates"
        )

    return {
        # str() first: Decimal(float) would reintroduce binary rounding error.
        "total": Decimal(str(row.total_revenue)),
        "count": count,
        "currency": row.currency or "USD",
    }


async def list_tenant_properties(tenant_id: str) -> List[Dict[str, Any]]:
    """List the properties owned by one tenant."""
    await db_pool.initialize()

    async with db_pool.get_session() as session:
        result = await session.execute(
            text("""
                SELECT id, name, timezone
                FROM properties
                WHERE tenant_id = :tenant_id
                ORDER BY name
            """),
            {"tenant_id": tenant_id},
        )
        return [
            {"id": row.id, "name": row.name, "timezone": row.timezone}
            for row in result.fetchall()
        ]


async def calculate_monthly_revenue(
    property_id: str, tenant_id: str, month: int, year: int
) -> Dict[str, Any]:
    """Calculate revenue for a calendar month in the property's own timezone."""
    await db_pool.initialize()

    async with db_pool.get_session() as session:
        property_timezone = await _get_property_timezone(session, property_id, tenant_id)
        start_utc, end_utc = month_bounds_utc(month, year, property_timezone)
        aggregate = await _aggregate_revenue(session, property_id, tenant_id, start_utc, end_utc)

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": str(aggregate["total"]),
        "currency": aggregate["currency"],
        "count": aggregate["count"],
        "period": f"{year:04d}-{month:02d}",
        "timezone": property_timezone,
    }


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """Aggregate all-time revenue for a property from the database."""
    await db_pool.initialize()

    async with db_pool.get_session() as session:
        property_timezone = await _get_property_timezone(session, property_id, tenant_id)
        aggregate = await _aggregate_revenue(session, property_id, tenant_id)

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": str(aggregate["total"]),
        "currency": aggregate["currency"],
        "count": aggregate["count"],
        "period": "all-time",
        "timezone": property_timezone,
    }
