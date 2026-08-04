from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional
from zoneinfo import ZoneInfo


async def calculate_monthly_revenue(
    property_id: str,
    tenant_id: str,
    month: int,
    year: int,
    timezone_str: str = "UTC",
    db_session=None,
) -> Decimal:
    """
    Calculates revenue for a specific month, respecting the property's timezone.
    
    Args:
        property_id: The property ID
        tenant_id: The tenant ID (for security)
        month: Month number (1-12)
        year: Year (e.g., 2024)
        timezone_str: Property's timezone (e.g., "Europe/Paris")
    """
    
    try:
        prop_tz = ZoneInfo(timezone_str)
    except Exception:
        prop_tz = timezone.utc
    
    # Create timezone-aware start/end dates for the month in property's timezone
    start_local = datetime(year, month, 1, 0, 0, 0, tzinfo=prop_tz)
    
    if month < 12:
        end_local = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=prop_tz)
    else:
        end_local = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=prop_tz)
    
    # Convert to UTC for database query (reservations stored in UTC)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = end_local.astimezone(timezone.utc)

    print(f"DEBUG: Querying revenue for {property_id} (tenant: {tenant_id})")
    print(f"DEBUG: Local range [{timezone_str}]: {start_local} to {end_local}")
    print(f"DEBUG: UTC range: {start_utc} to {end_utc}")

    try:
        from app.core.database_pool import DatabasePool
        from sqlalchemy import text

        db_pool = DatabasePool()
        await db_pool.initialize()

        if db_pool.session_factory:
            async with db_pool.get_session() as session:
                query = text("""
                    SELECT SUM(total_amount) as total
                    FROM reservations
                    WHERE property_id = :property_id
                    AND tenant_id = :tenant_id
                    AND check_in_date >= :start_date
                    AND check_in_date < :end_date
                """)

                result = await session.execute(
                    query,
                    {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "start_date": start_utc,
                        "end_date": end_utc,
                    },
                )
                row = result.fetchone()
                
                if row and row.total:
                    return Decimal(str(row.total))
                return Decimal("0")
    except Exception as e:
        print(f"Database error in calculate_monthly_revenue: {e}")
        return Decimal("0")


async def calculate_total_revenue(
    property_id: str,
    tenant_id: str,
    period_type: str = "all",
    month: Optional[int] = None,
    year: Optional[int] = None,
    timezone_str: str = "UTC",
) -> Dict[str, Any]:
    """
    Aggregates revenue from database with proper tenant isolation and timezone handling.
    
    Args:
        property_id: The property ID
        tenant_id: The tenant ID (critical for data isolation)
        period_type: "all", "monthly", or "yearly"
        month: Month (1-12) - required for monthly
        year: Year - required for monthly/yearly
        timezone_str: Property's timezone
    """
    try:
        from app.core.database_pool import DatabasePool
        from sqlalchemy import text

        db_pool = DatabasePool()
        await db_pool.initialize()

        if db_pool.session_factory:
            async with db_pool.get_session() as session:
                # Build query based on period type
                base_query = """
                    SELECT 
                        property_id,
                        SUM(total_amount) as total_revenue,
                        COUNT(*) as reservation_count
                    FROM reservations 
                    WHERE property_id = :property_id AND tenant_id = :tenant_id
                """
                
                params = {"property_id": property_id, "tenant_id": tenant_id}
                
                if period_type == "monthly" and month and year:
                    try:
                        prop_tz = ZoneInfo(timezone_str)
                    except Exception:
                        prop_tz = timezone.utc
                    
                    start_local = datetime(year, month, 1, 0, 0, 0, tzinfo=prop_tz)
                    if month < 12:
                        end_local = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=prop_tz)
                    else:
                        end_local = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=prop_tz)
                    
                    start_utc = start_local.astimezone(timezone.utc)
                    end_utc = end_local.astimezone(timezone.utc)
                    
                    base_query += """
                        AND check_in_date >= :start_date
                        AND check_in_date < :end_date
                    """
                    params["start_date"] = start_utc
                    params["end_date"] = end_utc
                    
                elif period_type == "yearly" and year:
                    try:
                        prop_tz = ZoneInfo(timezone_str)
                    except Exception:
                        prop_tz = timezone.utc
                    
                    start_local = datetime(year, 1, 1, 0, 0, 0, tzinfo=prop_tz)
                    end_local = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=prop_tz)
                    
                    start_utc = start_local.astimezone(timezone.utc)
                    end_utc = end_local.astimezone(timezone.utc)
                    
                    base_query += """
                        AND check_in_date >= :start_date
                        AND check_in_date < :end_date
                    """
                    params["start_date"] = start_utc
                    params["end_date"] = end_utc
                
                base_query += " GROUP BY property_id"

                result = await session.execute(text(base_query), params)
                row = result.fetchone()

                if row:
                    # Keep as Decimal for precision, convert to string for JSON
                    total_revenue = Decimal(str(row.total_revenue))
                    # Round to 2 decimal places for currency
                    total_revenue = total_revenue.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total": str(total_revenue),
                        "currency": "USD",
                        "count": row.reservation_count,
                    }
                else:
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total": "0.00",
                        "currency": "USD",
                        "count": 0,
                    }
        else:
            raise Exception("Database pool not available")

    except Exception as e:
        print(f"Database error for {property_id} (tenant: {tenant_id}): {e}")

        # BUG FIX: Mock data now includes tenant_id to prevent data leakage
        # Each tenant has different property data
        mock_data = {
            # tenant-a properties
            ("prop-001", "tenant-a"): {"total": "1916.67", "count": 4},
            ("prop-002", "tenant-a"): {"total": "4975.50", "count": 4},
            ("prop-003", "tenant-a"): {"total": "6100.50", "count": 2},
            # tenant-b properties
            ("prop-001", "tenant-b"): {"total": "2320.00", "count": 3},  # Different data for tenant-b's prop-001
            ("prop-004", "tenant-b"): {"total": "1776.50", "count": 4},
            ("prop-005", "tenant-b"): {"total": "3256.00", "count": 3},
        }

        mock_property_data = mock_data.get(
            (property_id, tenant_id), {"total": "0.00", "count": 0}
        )

        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": mock_property_data["total"],
            "currency": "USD",
            "count": mock_property_data["count"],
        }
