from datetime import datetime
from decimal import Decimal
from typing import Dict, Any

from sqlalchemy import text

from app.core.database_pool import db_pool

async def _get_pool():
    """
    Return the shared database pool, initializing it on first use.
    """
    if not db_pool.session_factory:
        await db_pool.initialize()
    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available")
    return db_pool

def _month_bounds(month: int, year: int):
    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    return start, end

async def property_belongs_to_tenant(property_id: str, tenant_id: str) -> bool:
    """True if the property exists under this tenant. Used to stop a tenant
    requesting another tenant's property (IDs are only unique per tenant)."""
    pool = await _get_pool()
    async with pool.get_session() as session:
        result = await session.execute(
            text("SELECT 1 FROM properties WHERE id = :property_id AND tenant_id = :tenant_id"),
            {"property_id": property_id, "tenant_id": tenant_id},
        )
        return result.first() is not None

async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Decimal:
    """
    Calculates revenue for a specific month.
    """
    start_local, end_local = _month_bounds(month, year)

    pool = await _get_pool()
    async with pool.get_session() as session:
        query = text("""
            SELECT COALESCE(SUM(r.total_amount), 0) AS total
            FROM reservations r
            JOIN properties p
              ON p.id = r.property_id AND p.tenant_id = r.tenant_id
            WHERE r.property_id = :property_id
              AND r.tenant_id = :tenant_id
              AND (r.check_in_date AT TIME ZONE p.timezone) >= :start_local
              AND (r.check_in_date AT TIME ZONE p.timezone) <  :end_local
        """)
        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_local": start_local,
            "end_local": end_local,
        })
        total = result.scalar_one()
        return Decimal(str(total))

async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    pool = await _get_pool()
    async with pool.get_session() as session:
        query = text("""
            SELECT
                property_id,
                SUM(total_amount) AS total_revenue,
                COUNT(*) AS reservation_count
            FROM reservations
            WHERE property_id = :property_id AND tenant_id = :tenant_id
            GROUP BY property_id
        """)
        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
        })
        row = result.fetchone()

    if row:
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": str(Decimal(str(row.total_revenue))),
            "currency": "USD",
            "count": row.reservation_count,
        }

    # No reservations found for this property
    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": "0.00",
        "currency": "USD",
        "count": 0,
        }
