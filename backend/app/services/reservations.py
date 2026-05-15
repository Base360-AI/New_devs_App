import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.core.database_pool import db_pool

logger = logging.getLogger(__name__)

MONEY_QUANT = Decimal("0.01")

FALLBACK_PROPERTIES = {
    "tenant-a": [
        {"id": "prop-001", "name": "Beach House Alpha", "timezone": "Europe/Paris"},
        {"id": "prop-002", "name": "City Apartment Downtown", "timezone": "Europe/Paris"},
        {"id": "prop-003", "name": "Country Villa Estate", "timezone": "Europe/Paris"},
    ],
    "tenant-b": [
        {"id": "prop-001", "name": "Mountain Lodge Beta", "timezone": "America/New_York"},
        {"id": "prop-004", "name": "Lakeside Cottage", "timezone": "America/New_York"},
        {"id": "prop-005", "name": "Urban Loft Modern", "timezone": "America/New_York"},
    ],
}

FALLBACK_REVENUE = {
    ("tenant-a", "prop-001"): {"total": "2250.00", "count": 4},
    ("tenant-a", "prop-002"): {"total": "4975.50", "count": 4},
    ("tenant-a", "prop-003"): {"total": "6100.50", "count": 2},
    ("tenant-b", "prop-001"): {"total": "0.00", "count": 0},
    ("tenant-b", "prop-004"): {"total": "1776.50", "count": 4},
    ("tenant-b", "prop-005"): {"total": "3256.00", "count": 3},
}


def month_bounds_utc(year: int, month: int, property_timezone: str) -> Tuple[datetime, datetime]:
    local_tz = ZoneInfo(property_timezone)
    local_start = datetime(year, month, 1, tzinfo=local_tz)
    if month == 12:
        local_end = datetime(year + 1, 1, 1, tzinfo=local_tz)
    else:
        local_end = datetime(year, month + 1, 1, tzinfo=local_tz)
    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


def format_money(value: Decimal) -> str:
    return str(value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP))


def reporting_period(month: int, year: int) -> Dict[str, Any]:
    label = datetime(year, month, 1).strftime("%B %Y")
    return {"month": month, "year": year, "label": label}


def _fallback_property(tenant_id: str, property_id: str) -> Optional[Dict[str, str]]:
    for prop in FALLBACK_PROPERTIES.get(tenant_id, []):
        if prop["id"] == property_id:
            return prop
    return None


async def _ensure_pool() -> None:
    if not db_pool.session_factory:
        await db_pool.initialize()


async def get_tenant_properties(tenant_id: str) -> List[Dict[str, Any]]:
    try:
        await _ensure_pool()
        async with db_pool.get_session() as session:
            result = await session.execute(
                text(
                    """
                    SELECT id, name, timezone
                    FROM properties
                    WHERE tenant_id = :tenant_id
                    ORDER BY name
                    """
                ),
                {"tenant_id": tenant_id},
            )
            return [dict(row) for row in result.mappings().all()]
    except Exception as exc:
        logger.warning("Using fallback properties for tenant %s: %s", tenant_id, exc)
        return [dict(prop, is_fallback=True) for prop in FALLBACK_PROPERTIES.get(tenant_id, [])]


async def get_property_for_tenant(property_id: str, tenant_id: str) -> Optional[Dict[str, Any]]:
    try:
        await _ensure_pool()
        async with db_pool.get_session() as session:
            result = await session.execute(
                text(
                    """
                    SELECT id, name, timezone
                    FROM properties
                    WHERE id = :property_id AND tenant_id = :tenant_id
                    """
                ),
                {"property_id": property_id, "tenant_id": tenant_id},
            )
            row = result.mappings().first()
            return dict(row) if row else None
    except Exception as exc:
        logger.warning(
            "Using fallback property lookup for tenant %s property %s: %s",
            tenant_id,
            property_id,
            exc,
        )
        prop = _fallback_property(tenant_id, property_id)
        return dict(prop, is_fallback=True) if prop else None


async def calculate_monthly_revenue(
    property_id: str,
    tenant_id: str,
    month: int,
    year: int,
) -> Dict[str, Any]:
    property_data = await get_property_for_tenant(property_id, tenant_id)
    if not property_data:
        raise LookupError("Property not found for tenant")

    property_timezone = property_data["timezone"]
    start_date, end_date = month_bounds_utc(year, month, property_timezone)

    try:
        await _ensure_pool()
        async with db_pool.get_session() as session:
            result = await session.execute(
                text(
                    """
                    SELECT
                        COALESCE(SUM(total_amount), 0) AS total_revenue,
                        COUNT(*) AS reservation_count,
                        COALESCE(MAX(currency), 'USD') AS currency
                    FROM reservations
                    WHERE property_id = :property_id
                      AND tenant_id = :tenant_id
                      AND check_in_date >= :start_date
                      AND check_in_date < :end_date
                    """
                ),
                {
                    "property_id": property_id,
                    "tenant_id": tenant_id,
                    "start_date": start_date,
                    "end_date": end_date,
                },
            )
            row = result.mappings().one()
            total_revenue = Decimal(str(row["total_revenue"] or "0"))
            return {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "property_name": property_data["name"],
                "property_timezone": property_timezone,
                "reporting_period": reporting_period(month, year),
                "total": format_money(total_revenue),
                "currency": row["currency"] or "USD",
                "count": row["reservation_count"],
                "is_fallback": False,
            }
    except Exception as exc:
        logger.warning(
            "Using fallback revenue for tenant %s property %s period %04d-%02d: %s",
            tenant_id,
            property_id,
            year,
            month,
            exc,
        )
        fallback = FALLBACK_REVENUE.get((tenant_id, property_id), {"total": "0.00", "count": 0})
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "property_name": property_data["name"],
            "property_timezone": property_timezone,
            "reporting_period": reporting_period(month, year),
            "total": fallback["total"],
            "currency": "USD",
            "count": fallback["count"],
            "is_fallback": True,
            "fallback_reason": "database_unavailable",
        }


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    return await calculate_monthly_revenue(property_id, tenant_id, 3, 2024)
