from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict
from zoneinfo import ZoneInfo


async def _fetch_monthly_summary(session, property_id: str, tenant_id: str, month: int, year: int) -> Dict[str, Any]:
    from sqlalchemy import text

    tz_query = text("""
        SELECT timezone
        FROM properties
        WHERE id = :property_id AND tenant_id = :tenant_id
        LIMIT 1
    """)
    tz_result = await session.execute(tz_query, {"property_id": property_id, "tenant_id": tenant_id})
    tz_row = tz_result.fetchone()
    property_tz = tz_row.timezone if tz_row and tz_row.timezone else "UTC"

    zone = ZoneInfo(property_tz)
    start_local = datetime(year, month, 1, tzinfo=zone)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, tzinfo=zone)
    else:
        end_local = datetime(year, month + 1, 1, tzinfo=zone)

    query = text("""
        SELECT
            property_id,
            COALESCE(SUM(total_amount), 0) AS total_revenue,
            COUNT(*) AS reservation_count,
            COALESCE(MAX(currency), 'USD') AS currency
        FROM reservations
        WHERE property_id = :property_id
          AND tenant_id = :tenant_id
          AND check_in_date >= :start_date
          AND check_in_date < :end_date
        GROUP BY property_id
    """)

    result = await session.execute(
        query,
        {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_date": start_local.astimezone(timezone.utc),
            "end_date": end_local.astimezone(timezone.utc),
        },
    )
    row = result.fetchone()

    if row:
        total_revenue = Decimal(str(row.total_revenue)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": str(total_revenue),
            "currency": row.currency or "USD",
            "count": row.reservation_count,
            "month": month,
            "year": year,
            "timezone": property_tz,
        }

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": "0.00",
        "currency": "USD",
        "count": 0,
        "month": month,
        "year": year,
        "timezone": property_tz,
    }


async def calculate_monthly_revenue(
    property_id: str,
    tenant_id: str,
    month: int,
    year: int,
    db_session=None,
) -> Dict[str, Any]:
    """Calculate a property's revenue for one month in the property's timezone."""

    try:
        from app.core.database_pool import DatabasePool

        if db_session is not None:
            return await _fetch_monthly_summary(db_session, property_id, tenant_id, month, year)

        db_pool = DatabasePool()
        await db_pool.initialize()

        if not db_pool.session_factory:
            raise Exception("Database pool not available")

        async with (await db_pool.get_session()) as session:
            return await _fetch_monthly_summary(session, property_id, tenant_id, month, year)

    except Exception as e:
        # Database unavailable or error occurred. Return a safe zeroed response
        # to avoid leaking mocked financial data across tenants.
        print(f"Database error for {property_id} (tenant: {tenant_id}): {e}")
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": "0.00",
            "currency": "USD",
            "count": 0,
            "month": month,
            "year": year,
            "timezone": "UTC",
        }


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """Aggregate revenue for the current month."""

    now = datetime.now(timezone.utc)
    return await calculate_monthly_revenue(property_id, tenant_id, now.month, now.year)
