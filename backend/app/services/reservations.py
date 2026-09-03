import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy import text
from app.core.database_pool import db_pool

logger = logging.getLogger(__name__)


class PropertyNotFoundError(Exception):
    """Raised when a property is not found for a given tenant."""
    pass


class MixedCurrencyError(ValueError):
    """Raised when reservations for a property reporting period contain multiple distinct currencies."""
    pass


async def get_tenant_property(property_id: str, tenant_id: str, session=None) -> Optional[Dict[str, Any]]:
    """
    Get a property verifying that it belongs to the specified tenant.
    """
    if session:
        query = text("""
            SELECT id, tenant_id, name, timezone
            FROM properties
            WHERE id = :property_id AND tenant_id = :tenant_id
        """)
        result = await session.execute(query, {"property_id": property_id, "tenant_id": tenant_id})
        row = result.fetchone()
        if not row:
            return None
        return {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "name": row.name,
            "timezone": row.timezone
        }

    async with db_pool.get_session() as session:
        return await get_tenant_property(property_id, tenant_id, session)


async def get_tenant_properties(tenant_id: str) -> List[Dict[str, Any]]:
    """
    Get all properties owned by a specific tenant.
    """
    async with db_pool.get_session() as session:
        query = text("""
            SELECT id, tenant_id, name, timezone
            FROM properties
            WHERE tenant_id = :tenant_id
            ORDER BY id
        """)
        result = await session.execute(query, {"tenant_id": tenant_id})
        rows = result.fetchall()
        return [
            {
                "id": row.id,
                "tenant_id": row.tenant_id,
                "name": row.name,
                "timezone": row.timezone
            }
            for row in rows
        ]


def get_month_utc_range(year: int, month: int, tz_name: str) -> tuple[datetime, datetime]:
    """
    Constructs a half-open UTC interval [start_utc, end_utc) for a given calendar month
    in the property's local IANA timezone. Fails loudly for invalid or unknown IANA timezone data.
    """
    if not tz_name or not isinstance(tz_name, str):
        raise ZoneInfoNotFoundError(f"Invalid or missing timezone: {tz_name!r}")

    local_tz = ZoneInfo(tz_name)
    local_start = datetime(year, month, 1, 0, 0, 0, tzinfo=local_tz)
    if month == 12:
        local_end = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=local_tz)
    else:
        local_end = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=local_tz)

    start_utc = local_start.astimezone(timezone.utc)
    end_utc = local_end.astimezone(timezone.utc)
    return start_utc, end_utc


async def calculate_monthly_revenue(
    property_id: str,
    tenant_id: str,
    year: int = 2024,
    month: int = 3
) -> Dict[str, Any]:
    """
    Calculates revenue for a specific property and month, respecting the property's
    local timezone and preserving financial cent precision.
    """
    async with db_pool.get_session() as session:
        prop = await get_tenant_property(property_id, tenant_id, session)
        if not prop:
            raise PropertyNotFoundError(f"Property '{property_id}' not found for tenant '{tenant_id}'")

        start_utc, end_utc = get_month_utc_range(year, month, prop["timezone"])

        query = text("""
            SELECT
                COALESCE(currency, 'USD') as currency,
                SUM(total_amount) as total_revenue,
                COUNT(*) as reservation_count
            FROM reservations
            WHERE property_id = :property_id
              AND tenant_id = :tenant_id
              AND check_in_date >= :start_utc
              AND check_in_date < :end_utc
            GROUP BY COALESCE(currency, 'USD')
        """)

        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "start_utc": start_utc,
            "end_utc": end_utc
        })
        rows = result.fetchall()

        if not rows:
            return {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "year": year,
                "month": month,
                "total": "0.00",
                "currency": "USD",
                "count": 0
            }

        if len(rows) > 1:
            currencies = sorted([r.currency for r in rows])
            raise MixedCurrencyError(
                f"Multiple currencies detected for property '{property_id}' in {year}-{month:02d}: {', '.join(currencies)}"
            )

        row = rows[0]
        total_amount = Decimal(str(row.total_revenue)) if row.total_revenue is not None else Decimal("0.00")
        quantized_total = total_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        count = int(row.reservation_count) if row.reservation_count is not None else 0
        currency = row.currency or "USD"

        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "year": year,
            "month": month,
            "total": f"{quantized_total:.2f}",
            "currency": currency,
            "count": count
        }


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Default revenue calculation wrapper for backwards compatibility (March 2024).
    """
    return await calculate_monthly_revenue(property_id, tenant_id, year=2024, month=3)
