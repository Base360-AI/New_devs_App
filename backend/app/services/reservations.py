from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List

from sqlalchemy import text

from app.core.database_pool import db_pool


def _to_money(value) -> str:
    """Round an amount to cents. Amounts are stored with sub-cent precision."""
    return str(Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


async def _session():
    await db_pool.initialize()
    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available")
    return db_pool.session_factory()


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue for a property, scoped to its tenant.
    """
    async with await _session() as session:
        query = text("""
            SELECT SUM(total_amount) as total_revenue,
                   COUNT(*) as reservation_count
            FROM reservations
            WHERE property_id = :property_id AND tenant_id = :tenant_id
        """)
        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
        })
        row = result.fetchone()

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": _to_money(row.total_revenue if row else 0),
        "currency": "USD",
        "count": row.reservation_count if row else 0,
    }


async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Dict[str, Any]:
    """
    Calculates revenue for a specific month, measured in the property's own
    timezone so a booking is counted in the month it is local to.
    """
    async with await _session() as session:
        # The month boundaries are expressed in each property's local time, so a
        # late-night check-in in Paris counts as the next day's month, not UTC's.
        query = text("""
            SELECT SUM(r.total_amount) as total_revenue,
                   COUNT(*) as reservation_count
            FROM reservations r
            JOIN properties p ON p.id = r.property_id AND p.tenant_id = r.tenant_id
            WHERE r.property_id = :property_id
              AND r.tenant_id = :tenant_id
              AND r.check_in_date >= (make_timestamp(:year, :month, 1, 0, 0, 0) AT TIME ZONE p.timezone)
              AND r.check_in_date <  ((make_timestamp(:year, :month, 1, 0, 0, 0) + INTERVAL '1 month') AT TIME ZONE p.timezone)
        """)
        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "year": year,
            "month": month,
        })
        row = result.fetchone()

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": _to_money(row.total_revenue if row else 0),
        "currency": "USD",
        "count": row.reservation_count if row else 0,
    }


async def list_tenant_properties(tenant_id: str) -> List[Dict[str, Any]]:
    """Returns the properties owned by a tenant, for the dashboard selector."""
    async with await _session() as session:
        query = text("""
            SELECT id, name, timezone
            FROM properties
            WHERE tenant_id = :tenant_id
            ORDER BY name
        """)
        result = await session.execute(query, {"tenant_id": tenant_id})
        rows = result.fetchall()

    return [{"id": r.id, "name": r.name, "timezone": r.timezone} for r in rows]


async def property_belongs_to_tenant(property_id: str, tenant_id: str) -> bool:
    """Whether a property is owned by the given tenant."""
    async with await _session() as session:
        query = text("""
            SELECT 1 FROM properties
            WHERE id = :property_id AND tenant_id = :tenant_id
        """)
        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
        })
        return result.fetchone() is not None
