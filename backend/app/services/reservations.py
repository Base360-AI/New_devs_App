from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional

from sqlalchemy import text

from app.core.database_pool import db_pool

CENT = Decimal("0.01")


def round_money(amount: Decimal) -> Decimal:
    """Round once, at the end, to whole cents (half-up, like accounting)."""
    return Decimal(amount).quantize(CENT, rounding=ROUND_HALF_UP)


async def get_tenant_properties(tenant_id: str) -> List[Dict[str, Any]]:
    """Lists the properties that belong to a tenant."""
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        result = await session.execute(
            text("""
                SELECT id, name, timezone
                FROM properties
                WHERE tenant_id = :tenant_id
                ORDER BY id
            """),
            {"tenant_id": tenant_id},
        )
        return [{"id": r.id, "name": r.name, "timezone": r.timezone} for r in result]


async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Decimal:
    """
    Calculates revenue for a specific month.
    The month is evaluated in the property's own timezone, not UTC, so a
    booking at 23:30 UTC on Feb 29 in Paris counts in March.
    """
    start_date = datetime(year, month, 1)
    if month < 12:
        end_date = datetime(year, month + 1, 1)
    else:
        end_date = datetime(year + 1, 1, 1)

    query = text("""
        SELECT COALESCE(SUM(r.total_amount), 0) AS total
        FROM reservations r
        JOIN properties p
            ON p.id = r.property_id AND p.tenant_id = r.tenant_id
        WHERE r.property_id = :property_id
        AND r.tenant_id = :tenant_id
        AND (r.check_in_date AT TIME ZONE p.timezone) >= :start_date
        AND (r.check_in_date AT TIME ZONE p.timezone) < :end_date
    """)

    await db_pool.initialize()
    async with db_pool.get_session() as session:
        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_date": start_date,
            "end_date": end_date,
        })
        return round_money(result.scalar_one())


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    """
    Aggregates revenue from database for one property of one tenant.
    Returns None when the property does not belong to the tenant.
    """
    # LEFT JOIN from properties so that an owned property with no bookings
    # returns 0, while a property of another tenant returns no row at all.
    query = text("""
        SELECT
            p.id AS property_id,
            COALESCE(SUM(r.total_amount), 0) AS total_revenue,
            COUNT(r.id) AS reservation_count
        FROM properties p
        LEFT JOIN reservations r
            ON r.property_id = p.id AND r.tenant_id = p.tenant_id
        WHERE p.id = :property_id AND p.tenant_id = :tenant_id
        GROUP BY p.id
    """)

    await db_pool.initialize()
    async with db_pool.get_session() as session:
        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id
        })
        row = result.fetchone()

    if row is None:
        return None

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": str(round_money(row.total_revenue)),
        "currency": "USD",
        "count": row.reservation_count,
    }
