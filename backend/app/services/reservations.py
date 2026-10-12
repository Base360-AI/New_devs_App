from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional

CENT = Decimal("0.01")


class PropertyNotFoundError(Exception):
    """Raised when a property does not exist for the requesting tenant."""

    def __init__(self, property_id: str, tenant_id: str):
        super().__init__(f"Property {property_id} not found for tenant {tenant_id}")
        self.property_id = property_id
        self.tenant_id = tenant_id


def to_cents(value) -> Decimal:
    """Round a monetary amount to 2 decimals (half-up). Done once, at the very end."""
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


async def calculate_monthly_revenue(
    property_id: str,
    month: int,
    year: int,
    db_session=None,
    tenant_id: Optional[str] = None,
) -> Decimal:
    """
    Calculates revenue for a specific month.

    Month boundaries are computed in the PROPERTY'S local time zone (properties.timezone),
    not UTC, so a reservation checking in at 2024-02-29 23:30 UTC is counted in March
    for a property in Europe/Paris.
    """
    if not tenant_id:
        raise ValueError("tenant_id is required to calculate revenue")

    # Local (naive) month boundaries - interpreted in the property's time zone by SQL below.
    start_date = datetime(year, month, 1)
    if month < 12:
        end_date = datetime(year, month + 1, 1)
    else:
        end_date = datetime(year + 1, 1, 1)

    from sqlalchemy import text
    from app.core.database_pool import db_pool

    await db_pool.initialize()
    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available")

    query = text("""
        SELECT COALESCE(SUM(r.total_amount), 0) AS total
        FROM reservations r
        JOIN properties p
          ON p.id = r.property_id AND p.tenant_id = r.tenant_id
        WHERE r.property_id = :property_id
          AND r.tenant_id = :tenant_id
          AND (r.check_in_date AT TIME ZONE p.timezone) >= :start_date
          AND (r.check_in_date AT TIME ZONE p.timezone) <  :end_date
    """)

    async with db_pool.get_session() as session:
        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_date": start_date,
            "end_date": end_date,
        })
        total = result.scalar() or Decimal("0")

    return to_cents(total)

async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    # Import database pool (shared instance - initialized once)
    from app.core.database_pool import db_pool
    from sqlalchemy import text

    await db_pool.initialize()

    if not db_pool.session_factory:
        # Fail loudly instead of returning fabricated numbers for a financial report.
        raise RuntimeError("Database pool not available")

    async with db_pool.get_session() as session:
        # Start from properties so we can tell "unknown property for this tenant"
        # apart from "known property with no bookings yet".
        query = text("""
            SELECT
                p.id AS property_id,
                COALESCE(SUM(r.total_amount), 0) as total_revenue,
                COUNT(r.id) as reservation_count
            FROM properties p
            LEFT JOIN reservations r
              ON r.property_id = p.id AND r.tenant_id = p.tenant_id
            WHERE p.id = :property_id AND p.tenant_id = :tenant_id
            GROUP BY p.id
        """)

        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id
        })
        row = result.fetchone()

    if row is None:
        # Not this tenant's property (or doesn't exist). Don't report fake zeros.
        raise PropertyNotFoundError(property_id, tenant_id)

    # Sum exactly in NUMERIC/Decimal, round to cents ONCE at the end.
    total_revenue = to_cents(row.total_revenue)
    count = row.reservation_count

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": str(total_revenue),
        "currency": "USD",
        "count": count
    }


async def list_tenant_properties(tenant_id: str) -> List[Dict[str, Any]]:
    """
    Lists the properties owned by a tenant (id, name, timezone).
    """
    from app.core.database_pool import db_pool
    from sqlalchemy import text

    await db_pool.initialize()

    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available")

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
        rows = result.fetchall()

    return [{"id": r.id, "name": r.name, "timezone": r.timezone} for r in rows]
