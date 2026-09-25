from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List

async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Decimal:
    """
    Calculates revenue for a specific month, respecting the property's local timezone.
    """
    import asyncpg
    from app.config import settings

    start_date = datetime(year, month, 1)
    if month < 12:
        end_date = datetime(year, month + 1, 1)
    else:
        end_date = datetime(year + 1, 1, 1)

    conn = await asyncpg.connect(settings.database_url)
    try:
        row = await conn.fetchrow(
            """
            SELECT COALESCE(SUM(r.total_amount), 0) AS total
            FROM reservations r
            JOIN properties p ON r.property_id = p.id AND r.tenant_id = p.tenant_id
            WHERE r.property_id = $1
              AND r.tenant_id   = $2
              AND (r.check_in_date AT TIME ZONE p.timezone) >= $3
              AND (r.check_in_date AT TIME ZONE p.timezone) <  $4
            """,
            property_id,
            tenant_id,
            start_date,
            end_date,
        )
    finally:
        await conn.close()

    return Decimal(str(row["total"])) if row else Decimal("0")

async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    try:
        import asyncpg
        from app.config import settings

        conn = await asyncpg.connect(settings.database_url)
        try:
            row = await conn.fetchrow(
                """
                SELECT
                    property_id,
                    SUM(total_amount)  AS total_revenue,
                    COUNT(*)           AS reservation_count
                FROM reservations
                WHERE property_id = $1 AND tenant_id = $2
                GROUP BY property_id
                """,
                property_id,
                tenant_id,
            )
        finally:
            await conn.close()

        if row:
            total_revenue = Decimal(str(row["total_revenue"]))
            return {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "total": str(total_revenue),
                "currency": "USD",
                "count": row["reservation_count"],
            }
        else:
            return {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "total": "0.00",
                "currency": "USD",
                "count": 0,
            }

    except Exception as e:
        print(f"Database error for {property_id} (tenant: {tenant_id}): {e}")
        raise
