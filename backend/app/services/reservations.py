from decimal import Decimal
from typing import Dict, Any, List, Optional

async def list_tenant_properties(tenant_id: str) -> List[Dict[str, Any]]:
    """
    Lists the properties owned by one tenant.

    Raises if the database is unavailable, so callers never receive stand-in data.
    """
    from sqlalchemy import text
    from app.core.database_pool import db_pool

    await db_pool.initialize()
    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available")

    query = text("""
        SELECT id, name, timezone
        FROM properties
        WHERE tenant_id = :tenant_id
        ORDER BY name
    """)

    async with db_pool.get_session() as session:
        result = await session.execute(query, {"tenant_id": tenant_id})
        rows = result.fetchall()

    return [
        {"id": row.id, "name": row.name, "timezone": row.timezone}
        for row in rows
    ]

async def calculate_total_revenue(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """
    Aggregates revenue from database, optionally limited to one calendar month.

    Month boundaries are taken in the property's own timezone, so a stay that
    checks in at 00:30 on 1 March in Paris counts toward March even though it
    is still 29 February in UTC.

    Returns None when the property does not exist for this tenant.
    Raises if the database is unavailable, so callers never receive stand-in figures.
    """
    from sqlalchemy import text
    from app.core.database_pool import db_pool

    await db_pool.initialize()
    # [MOCK] Raise instead of silently returning the hardcoded mock_data table that used to live in the except block
    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available")

    # [LEAK] Start from the tenant's own property: another tenant's ID returns no row (404), an unbooked one returns 0
    query = text("""
        SELECT
            p.id AS property_id,
            COALESCE(SUM(r.total_amount), 0) AS total_revenue,
            COUNT(r.id) AS reservation_count
        FROM properties p
        LEFT JOIN reservations r
            ON r.property_id = p.id
            AND r.tenant_id = p.tenant_id
            -- [TZ] Month bounds use the property's timezone: res-tz-1 (29 Feb 23:30 UTC = 1 Mar 00:30 Paris) counts in March
            AND (
                CAST(:month AS INTEGER) IS NULL
                OR (
                    r.check_in_date >= (make_timestamp(:year, :month, 1, 0, 0, 0) AT TIME ZONE p.timezone)
                    AND r.check_in_date < ((make_timestamp(:year, :month, 1, 0, 0, 0) + INTERVAL '1 month') AT TIME ZONE p.timezone)
                )
            )
        WHERE p.id = :property_id AND p.tenant_id = :tenant_id
        GROUP BY p.id
    """)

    async with db_pool.get_session() as session:
        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "month": month,
            "year": year
        })
        row = result.fetchone()

    if row is None:
        return None

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "month": month,
        "year": year,
        "total": str(Decimal(str(row.total_revenue))),
        "currency": "USD",
        "count": row.reservation_count
    }
