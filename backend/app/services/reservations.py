from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, List
from zoneinfo import ZoneInfo


async def property_belongs_to_tenant(property_id: str, tenant_id: str) -> bool:
    """Return whether a property is owned by the requesting tenant."""
    from sqlalchemy import text
    from app.core.database_pool import db_pool

    if db_pool.session_factory is None:
        await db_pool.initialize()

    if db_pool.session_factory is None:
        raise RuntimeError("Database pool not available")

    async with db_pool.get_session() as session:
        result = await session.execute(
            text("""
                SELECT 1
                FROM properties
                WHERE id = :property_id AND tenant_id = :tenant_id
                LIMIT 1
            """),
            {"property_id": property_id, "tenant_id": tenant_id},
        )
        return result.scalar_one_or_none() is not None

async def calculate_monthly_revenue(
    property_id: str,
    month: int,
    year: int,
    tenant_id: str = None,
    db_session=None,
) -> Decimal:
    """
    Calculates revenue for a specific month.
    """

    if not tenant_id:
        raise ValueError("tenant_id is required for monthly revenue calculation")

    from sqlalchemy import text
    from app.core.database_pool import db_pool

    if db_session is None:
        if db_pool.session_factory is None:
            await db_pool.initialize()
        if db_pool.session_factory is None:
            raise RuntimeError("Database pool not available")

    property_query = text("""
        SELECT timezone
        FROM properties
        WHERE id = :property_id AND tenant_id = :tenant_id
    """)

    async def calculate(session) -> Decimal:
        property_result = await session.execute(property_query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
        })
        property_row = property_result.fetchone()
        if not property_row:
            raise ValueError("Property not found")

        property_timezone = ZoneInfo(property_row.timezone)
        start_date = datetime(year, month, 1, tzinfo=property_timezone)
        if month < 12:
            end_date = datetime(year, month + 1, 1, tzinfo=property_timezone)
        else:
            end_date = datetime(year + 1, 1, 1, tzinfo=property_timezone)

        result = await session.execute(text("""
            SELECT COALESCE(SUM(total_amount), 0) AS total
            FROM reservations
            WHERE property_id = :property_id
              AND tenant_id = :tenant_id
              AND check_in_date >= :start_date
              AND check_in_date < :end_date
        """), {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_date": start_date.astimezone(timezone.utc),
            "end_date": end_date.astimezone(timezone.utc),
        })
        return Decimal(str(result.scalar_one()))

    if db_session is not None:
        return await calculate(db_session)

    async with db_pool.get_session() as session:
        return await calculate(session)

async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    try:
        from app.core.database_pool import db_pool
        
        # Initialize pool if needed
        if db_pool.session_factory is None:
            await db_pool.initialize()
        
        if db_pool.session_factory:
            async with db_pool.get_session() as session:
                # Use SQLAlchemy text for raw SQL
                from sqlalchemy import text
                
                query = text("""
                    SELECT
                        property_id,
                        currency,
                        SUM(total_amount) as total_revenue,
                        COUNT(*) as reservation_count
                    FROM reservations 
                    WHERE property_id = :property_id AND tenant_id = :tenant_id
                    GROUP BY property_id, currency
                """)
                
                result = await session.execute(query, {
                    "property_id": property_id, 
                    "tenant_id": tenant_id
                })
                rows = result.fetchall()
                
                if len(rows) > 1:
                    raise ValueError("Cannot aggregate revenue across multiple currencies")

                if rows:
                    row = rows[0]
                    total_revenue = Decimal(str(row.total_revenue))
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total": str(total_revenue),
                        "currency": row.currency,
                        "count": row.reservation_count
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
        else:
            raise Exception("Database pool not available")
            
    except Exception as e:
        raise RuntimeError(
            f"Unable to calculate revenue for property {property_id}"
        ) from e
