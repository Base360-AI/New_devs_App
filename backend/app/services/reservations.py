from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Tuple
from zoneinfo import ZoneInfo

REPORT_YEAR = 2024
REPORT_MONTH = 3
_CENTS = Decimal("0.01")


def _quantize_money(amount: Decimal) -> Decimal:
    return amount.quantize(_CENTS, rounding=ROUND_HALF_UP)


def _empty_summary(property_id: str, tenant_id: str) -> Dict[str, Any]:
    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": "0.00",
        "currency": "USD",
        "count": 0,
    }


def _month_window(year: int, month: int, timezone_name: str) -> Tuple[datetime, datetime]:
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        tz = ZoneInfo("UTC")

    start_local = datetime(year, month, 1, tzinfo=tz)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, tzinfo=tz)
    else:
        end_local = datetime(year, month + 1, 1, tzinfo=tz)

    utc = ZoneInfo("UTC")
    return start_local.astimezone(utc), end_local.astimezone(utc)


async def _monthly_totals(
    property_id: str,
    tenant_id: str,
    year: int,
    month: int,
) -> Tuple[Decimal, int]:
    from app.core.database_pool import db_pool

    async with db_pool.get_connection() as connection:
        timezone_name = await connection.fetchval(
            """
            SELECT timezone
            FROM properties
            WHERE id = $1 AND tenant_id = $2
            """,
            property_id,
            tenant_id,
        )
        start_date, end_date = _month_window(year, month, timezone_name or "UTC")

        row = await connection.fetchrow(
            """
            SELECT
                COALESCE(SUM(total_amount), 0) AS total_revenue,
                COUNT(*) AS reservation_count
            FROM reservations
            WHERE property_id = $1
              AND tenant_id = $2
              AND check_in_date >= $3
              AND check_in_date < $4
            """,
            property_id,
            tenant_id,
            start_date,
            end_date,
        )

    total = Decimal(str(row["total_revenue"] if row else 0))
    count = int(row["reservation_count"] if row else 0)
    return _quantize_money(total), count


async def calculate_monthly_revenue(
    property_id: str,
    month: int,
    year: int,
    tenant_id: str,
) -> Decimal:
    total, _count = await _monthly_totals(property_id, tenant_id, year, month)
    return total


async def calculate_total_revenue(
    property_id: str,
    tenant_id: str,
    year: int = REPORT_YEAR,
    month: int = REPORT_MONTH,
) -> Dict[str, Any]:       
    try:
        total, count = await _monthly_totals(property_id, tenant_id, year, month)
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": f"{total:.2f}",
            "currency": "USD",
            "count": count,
        }
    except Exception as e:
        print(f"Database error for {property_id} (tenant: {tenant_id}): {e}")
        return _empty_summary(property_id, tenant_id)


async def list_tenant_properties(tenant_id: str) -> list:
    from app.core.database_pool import db_pool

    async with db_pool.get_connection() as connection:
        rows = await connection.fetch(
            """
            SELECT id, name
            FROM properties
            WHERE tenant_id = $1
            ORDER BY id
            """,
            tenant_id,
        )
        return [{"id": row["id"], "name": row["name"]} for row in rows]
