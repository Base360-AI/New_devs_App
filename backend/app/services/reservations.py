from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List

async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int, db_session=None) -> Decimal:
    """
    Calculates revenue for a specific month, using the property's local timezone
    to decide which month a check-in belongs to.
    """
    print(f"DEBUG: Querying revenue for {property_id} for {year}-{month:02d}")

    query = """
        SELECT SUM(r.total_amount) as total
        FROM reservations r
        JOIN properties p ON p.id = r.property_id AND p.tenant_id = r.tenant_id
        WHERE r.property_id = $1
        AND r.tenant_id = $2
        AND (r.check_in_date AT TIME ZONE p.timezone) >= make_timestamp($3, $4, 1, 0, 0, 0)
        AND (r.check_in_date AT TIME ZONE p.timezone) < make_timestamp($3, $4, 1, 0, 0, 0) + interval '1 month'
    """

    from app.core.database_pool import db_pool

    if db_pool.pool is None:
        await db_pool.initialize()

    async with db_pool.get_session() as conn:
        total = await conn.fetchval(query, property_id, tenant_id, year, month)

    return Decimal(str(total or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    # Import database pool
    from app.core.database_pool import db_pool

    # Initialize pool if needed
    if db_pool.pool is None:
        await db_pool.initialize()

    async with db_pool.get_session() as conn:
        query = """
            SELECT 
                property_id,
                SUM(total_amount) as total_revenue,
                COUNT(*) as reservation_count
            FROM reservations 
            WHERE property_id = $1 AND tenant_id = $2
            GROUP BY property_id
        """

        row = await conn.fetchrow(query, property_id, tenant_id)

    if row:
        total_revenue = Decimal(str(row["total_revenue"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": str(total_revenue),
            "currency": "USD", 
            "count": row["reservation_count"]
        }
    else:
        # No reservations found for this property
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": "0.00",
            "currency": "USD",
            "count": 0
        }
