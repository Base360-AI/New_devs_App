import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, AsyncIterator, Dict, List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database_pool import db_pool

logger = logging.getLogger(__name__)

CENT = Decimal("0.01")


class RevenueServiceError(RuntimeError):
    """A safe, client-facing classification for revenue service failures."""


class PropertyNotFoundError(LookupError):
    """The requested property does not belong to the authenticated tenant."""


@asynccontextmanager
async def _session_scope(
    db_session: Optional[AsyncSession] = None,
) -> AsyncIterator[AsyncSession]:
    if db_session is not None:
        yield db_session
        return

    async with db_pool.get_session() as session:
        yield session


def _month_boundaries_utc(year: int, month: int, timezone_name: str) -> tuple[datetime, datetime]:
    property_timezone = ZoneInfo(timezone_name)
    start_local = datetime(year, month, 1, tzinfo=property_timezone)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, tzinfo=property_timezone)
    else:
        end_local = datetime(year, month + 1, 1, tzinfo=property_timezone)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


async def get_properties_for_tenant(
    tenant_id: str,
    db_session: Optional[AsyncSession] = None,
) -> List[Dict[str, str]]:
    """Return only properties owned by the authenticated tenant."""
    try:
        async with _session_scope(db_session) as session:
            result = await session.execute(
                text(
                    """
                    SELECT id, name, timezone
                    FROM properties
                    WHERE tenant_id = :tenant_id
                    ORDER BY name, id
                    """
                ),
                {"tenant_id": tenant_id},
            )
            return [dict(row) for row in result.mappings().all()]
    except Exception as exc:
        logger.exception("Failed to load properties for tenant %s", tenant_id)
        raise RevenueServiceError("Property data is temporarily unavailable") from exc


async def calculate_total_revenue(
    property_id: str,
    tenant_id: str,
    year: int,
    month: int,
    db_session: Optional[AsyncSession] = None,
) -> Dict[str, Any]:
    """Calculate one tenant property's revenue for a property-local month."""
    try:
        async with _session_scope(db_session) as session:
            property_result = await session.execute(
                text(
                    """
                    SELECT id, name, timezone
                    FROM properties
                    WHERE id = :property_id AND tenant_id = :tenant_id
                    """
                ),
                {"property_id": property_id, "tenant_id": tenant_id},
            )
            property_row = property_result.mappings().first()
            if property_row is None:
                raise PropertyNotFoundError(property_id)

            start_utc, end_utc = _month_boundaries_utc(
                year, month, property_row["timezone"]
            )
            revenue_result = await session.execute(
                text(
                    """
                    SELECT
                        COALESCE(SUM(total_amount), 0) AS total_revenue,
                        COUNT(*) AS reservation_count,
                        COALESCE(MIN(currency), 'USD') AS currency,
                        COUNT(DISTINCT currency) AS currency_count
                    FROM reservations
                    WHERE property_id = :property_id
                      AND tenant_id = :tenant_id
                      AND check_in_date >= :start_utc
                      AND check_in_date < :end_utc
                    """
                ),
                {
                    "property_id": property_id,
                    "tenant_id": tenant_id,
                    "start_utc": start_utc,
                    "end_utc": end_utc,
                },
            )
            revenue_row = revenue_result.mappings().one()
            if revenue_row["currency_count"] > 1:
                raise RevenueServiceError(
                    "Revenue cannot be combined across multiple currencies"
                )

            total = Decimal(str(revenue_row["total_revenue"])).quantize(
                CENT, rounding=ROUND_HALF_UP
            )
            return {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "year": year,
                "month": month,
                "total": format(total, ".2f"),
                "currency": revenue_row["currency"],
                "count": int(revenue_row["reservation_count"]),
            }
    except (PropertyNotFoundError, RevenueServiceError):
        raise
    except Exception as exc:
        logger.exception(
            "Revenue query failed for tenant=%s property=%s year=%s month=%s",
            tenant_id,
            property_id,
            year,
            month,
        )
        raise RevenueServiceError("Revenue data is temporarily unavailable") from exc
