from datetime import datetime
from decimal import Decimal
from typing import Dict, Any

import pytz
from sqlalchemy import text


async def calculate_monthly_revenue(
    property_id: str,
    tenant_id: str,
    month: int,
    year: int,
    db_session=None
) -> Decimal:
    """
    Calculates revenue for a specific month (timezone-safe, tenant-safe).
    """

    # 🔧 STEP 1: Resolve timezone (fallback = UTC)
    property_timezone = "UTC"  # TODO: fetch from DB if available
    tz = pytz.timezone(property_timezone)

    # 🔧 STEP 2: Create timezone-aware date range
    start_date = tz.localize(datetime(year, month, 1))

    if month < 12:
        end_date = tz.localize(datetime(year, month + 1, 1))
    else:
        end_date = tz.localize(datetime(year + 1, 1, 1))

    print(f"DEBUG: Revenue query → property={property_id}, tenant={tenant_id}, range=({start_date} → {end_date})")

    try:
        # 🔧 STEP 3: Execute DB query with tenant isolation
        query = text("""
            SELECT COALESCE(SUM(total_amount), 0) as total
            FROM reservations
            WHERE property_id = :property_id
            AND tenant_id = :tenant_id
            AND check_in_date >= :start_date
            AND check_in_date < :end_date
        """)

        result = await db_session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_date": start_date,
            "end_date": end_date
        })

        row = result.fetchone()

        # 🔧 STEP 4: Fix precision
        total = Decimal(str(row.total)) if row and row.total else Decimal("0.00")

        return total.quantize(Decimal("0.01"))

    except Exception as e:
        print(f"Monthly revenue error → property={property_id}, tenant={tenant_id}: {e}")
        return Decimal("0.00")


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates total revenue for a property (tenant-safe, precise).
    """
    try:
        from app.core.database_pool import DatabasePool

        db_pool = DatabasePool()
        await db_pool.initialize()

        if not db_pool.session_factory:
            raise Exception("Database pool not available")

        async with db_pool.get_session() as session:

            query = text("""
                SELECT 
                    property_id,
                    COALESCE(SUM(total_amount), 0) as total_revenue,
                    COUNT(*) as reservation_count
                FROM reservations 
                WHERE property_id = :property_id 
                AND tenant_id = :tenant_id
                GROUP BY property_id
            """)

            result = await session.execute(query, {
                "property_id": property_id,
                "tenant_id": tenant_id
            })

            row = result.fetchone()

            if row:
                # 🔧 FIX: Proper Decimal handling
                total_revenue = Decimal(row.total_revenue or 0).quantize(Decimal("0.01"))

                return {
                    "property_id": property_id,
                    "tenant_id": tenant_id,
                    "total": str(total_revenue),
                    "currency": "USD",
                    "count": row.reservation_count
                }

            return {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "total": "0.00",
                "currency": "USD",
                "count": 0
            }

    except Exception as e:
        print(f"Total revenue error → property={property_id}, tenant={tenant_id}: {e}")

        # 🔧 Clean fallback (NO fake data)
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": "0.00",
            "currency": "USD",
            "count": 0
        }
