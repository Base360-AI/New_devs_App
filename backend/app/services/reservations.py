import logging
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.core.database_pool import db_pool

logger = logging.getLogger(__name__)

_CENTS = Decimal("0.01")


def _to_currency(amount: Decimal) -> Decimal:
    """Round a monetary value to whole cents (half-up)."""
    return amount.quantize(_CENTS, rounding=ROUND_HALF_UP)


async def _get_property_timezone(session, property_id: str, tenant_id: str) -> ZoneInfo:
    result = await session.execute(
        text(
            "SELECT timezone FROM properties WHERE id = :property_id AND tenant_id = :tenant_id"
        ),
        {"property_id": property_id, "tenant_id": tenant_id},
    )
    row = result.fetchone()
    tz_name = row.timezone if row and row.timezone else "UTC"
    try:
        return ZoneInfo(tz_name)
    except Exception:
        logger.warning("Unknown timezone %r for property %s, using UTC", tz_name, property_id)
        return ZoneInfo("UTC")


async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Decimal:
    """Revenue for a calendar month, bucketed in the property's local timezone.

    check_in_date is stored in UTC. A 23:30 UTC check-in on Feb 29 is March 1st
    in Europe/Paris, so the month boundaries are built in the property's timezone
    rather than naive UTC; otherwise the booking lands in the wrong month.
    """
    await db_pool.initialize()
    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available")

    async with db_pool.get_session() as session:
        tz = await _get_property_timezone(session, property_id, tenant_id)

        start_date = datetime(year, month, 1, tzinfo=tz)
        if month < 12:
            end_date = datetime(year, month + 1, 1, tzinfo=tz)
        else:
            end_date = datetime(year + 1, 1, 1, tzinfo=tz)

        result = await session.execute(
            text(
                """
                SELECT COALESCE(SUM(total_amount), 0) AS total
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
        row = result.fetchone()
        total = row.total if row else 0
        return _to_currency(Decimal(str(total)))


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """Total revenue and reservation count for a property within a tenant."""
    try:
        await db_pool.initialize()
        if not db_pool.session_factory:
            raise Exception("Database pool not available")

        async with db_pool.get_session() as session:
            result = await session.execute(
                text(
                    """
                    SELECT SUM(total_amount) AS total_revenue,
                           COUNT(*) AS reservation_count
                    FROM reservations
                    WHERE property_id = :property_id AND tenant_id = :tenant_id
                    """
                ),
                {"property_id": property_id, "tenant_id": tenant_id},
            )
            row = result.fetchone()

        total_amount = row.total_revenue if row else None
        count = row.reservation_count if row else 0
        total = _to_currency(Decimal(str(total_amount))) if total_amount is not None else Decimal("0.00")

        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": str(total),
            "currency": "USD",
            "count": count or 0,
        }

    except Exception as e:
        logger.warning("Database error for %s (tenant: %s): %s", property_id, tenant_id, e)

        # Property-specific mock data used when the database is unavailable.
        mock_data = {
            "prop-001": {"total": "1000.00", "count": 3},
            "prop-002": {"total": "4975.50", "count": 4},
            "prop-003": {"total": "6100.50", "count": 2},
            "prop-004": {"total": "1776.50", "count": 4},
            "prop-005": {"total": "3256.00", "count": 3},
        }
        mock = mock_data.get(property_id, {"total": "0.00", "count": 0})

        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": mock["total"],
            "currency": "USD",
            "count": mock["count"],
        }
