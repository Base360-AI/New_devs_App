from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from typing import Dict, Any, List, Optional, Tuple
from zoneinfo import ZoneInfo


def get_month_bounds_utc(year: int, month: int, timezone: str = "UTC") -> Tuple[datetime, datetime]:
    """
    Returns [start, end) of a month in the property's local time, converted to UTC.
    Example: March in Europe/Paris starts at 2024-02-29 23:00 UTC, not 2024-03-01 00:00 UTC.
    """
    local_tz = ZoneInfo(timezone)

    # Midnight on the 1st of this month and of next month, in the property's time zone
    start_local = datetime(year, month, 1, tzinfo=local_tz)
    if month < 12:
        end_local = datetime(year, month + 1, 1, tzinfo=local_tz)
    else:
        end_local = datetime(year + 1, 1, 1, tzinfo=local_tz)

    # check_in_date is stored in UTC, so compare against UTC bounds
    return start_local.astimezone(dt_timezone.utc), end_local.astimezone(dt_timezone.utc)


async def calculate_monthly_revenue(
    property_id: str,
    tenant_id: str,
    month: int,
    year: int,
    db_session=None,
    timezone: Optional[str] = None,
) -> Decimal:
    """
    Calculates revenue for one property, for one tenant, for one month.
    - db_session: a SQLAlchemy AsyncSession. If None, one is opened from DatabasePool.
    - timezone: the property's time zone. If None, it is read from the properties table.
    """
    if db_session is not None:
        return await _fetch_monthly_revenue(db_session, property_id, tenant_id, month, year, timezone)

    # No session given: open one from the shared pool
    from app.core.database_pool import db_pool

    await db_pool.initialize()
    if not db_pool.session_factory:
        raise Exception("Database pool not available")

    async with db_pool.get_session() as session:
        return await _fetch_monthly_revenue(session, property_id, tenant_id, month, year, timezone)


async def _fetch_monthly_revenue(session, property_id: str, tenant_id: str, month: int, year: int, timezone: Optional[str]) -> Decimal:
    """Runs the monthly revenue query on an open session."""
    from sqlalchemy import text

    # Look up the property's time zone if the caller didn't pass it
    if timezone is None:
        tz_result = await session.execute(
            text("SELECT timezone FROM properties WHERE id = :property_id AND tenant_id = :tenant_id"),
            {"property_id": property_id, "tenant_id": tenant_id},
        )
        timezone = tz_result.scalar()
        if timezone is None:
            # This tenant has no such property, so it has no revenue for it
            return Decimal("0")

    start_date, end_date = get_month_bounds_utc(year, month, timezone)

    print(f"DEBUG: Querying revenue for {property_id} (tenant: {tenant_id}) from {start_date} to {end_date}")

    # Filter by tenant too: the same property_id can exist for several tenants
    query = text("""
        SELECT SUM(total_amount) AS total
        FROM reservations
        WHERE property_id = :property_id
        AND tenant_id = :tenant_id
        AND check_in_date >= :start_date
        AND check_in_date < :end_date
    """)

    result = await session.execute(query, {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "start_date": start_date,
        "end_date": end_date,
    })

    # SUM() returns NULL when there are no reservations, so fall back to 0
    total = result.scalar()
    return total if total is not None else Decimal("0")

async def get_tenant_properties(tenant_id: str) -> List[Dict[str, Any]]:
    """Returns only this tenant's properties (id, name, timezone)."""
    from app.core.database_pool import db_pool
    from sqlalchemy import text

    await db_pool.initialize()
    if not db_pool.session_factory:
        raise Exception("Database pool not available")

    async with db_pool.get_session() as session:
        result = await session.execute(
            text("SELECT id, name, timezone FROM properties WHERE tenant_id = :tenant_id ORDER BY id"),
            {"tenant_id": tenant_id},
        )
        return [{"id": row.id, "name": row.name, "timezone": row.timezone} for row in result]


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    Errors are raised, never replaced by fake numbers: showing wrong revenue is worse than showing an error.
    """
    from app.core.database_pool import db_pool
    from sqlalchemy import text

    # Reuse the one shared pool (creating a new pool per request leaks connections)
    await db_pool.initialize()
    if not db_pool.session_factory:
        raise Exception("Database pool not available")

    async with db_pool.get_session() as session:
        query = text("""
            SELECT
                property_id,
                SUM(total_amount) as total_revenue,
                COUNT(*) as reservation_count
            FROM reservations
            WHERE property_id = :property_id AND tenant_id = :tenant_id
            GROUP BY property_id
        """)

        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id
        })
        row = result.fetchone()

        if row:
            total_revenue = Decimal(str(row.total_revenue))
            return {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "total": str(total_revenue),
                "currency": "USD",
                "count": row.reservation_count
            }

        # No reservations found for this property (for this tenant)
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": "0.00",
            "currency": "USD",
            "count": 0
        }
