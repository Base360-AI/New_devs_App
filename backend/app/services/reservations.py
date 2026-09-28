import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict
from zoneinfo import ZoneInfo


logger = logging.getLogger(__name__)


class RevenueServiceError(RuntimeError):
    """Raised when revenue data cannot be retrieved from the database."""


class PropertyNotFoundError(LookupError):
    """Raised when a property does not belong to the requesting tenant."""


async def calculate_monthly_revenue(
    property_id: str,
    tenant_id: str,
    year: int,
    month: int,
) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    try:
        # Use the application-wide database pool initialized at startup.
        from app.core.database_pool import db_pool
        
        async with db_pool.get_session() as session:
            # Use SQLAlchemy text for raw SQL
            from sqlalchemy import text

            property_query = text("""
                SELECT timezone
                FROM properties
                WHERE id = :property_id AND tenant_id = :tenant_id
                LIMIT 1
            """)
            property_result = await session.execute(property_query, {
                "property_id": property_id,
                "tenant_id": tenant_id
            })

            property_timezone = property_result.scalar_one_or_none()
            if property_timezone is None:
                raise PropertyNotFoundError("Property not found")

            local_timezone = ZoneInfo(property_timezone)
            start_local = datetime(year, month, 1, tzinfo=local_timezone)
            if month == 12:
                end_local = datetime(year + 1, 1, 1, tzinfo=local_timezone)
            else:
                end_local = datetime(year, month + 1, 1, tzinfo=local_timezone)

            start_utc = start_local.astimezone(timezone.utc)
            end_utc = end_local.astimezone(timezone.utc)

            query = text("""
                SELECT
                    property_id,
                    SUM(total_amount) AS total_revenue,
                    COUNT(*) AS reservation_count
                FROM reservations
                WHERE property_id = :property_id
                  AND tenant_id = :tenant_id
                  AND check_in_date >= :start_utc
                  AND check_in_date < :end_utc
                GROUP BY property_id
            """)

            result = await session.execute(query, {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "start_utc": start_utc,
                "end_utc": end_utc
            })
            row = result.fetchone()

            if row:
                total_revenue = Decimal(str(row.total_revenue)).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )
                return {
                    "property_id": property_id,
                    "tenant_id": tenant_id,
                    "total": format(total_revenue, ".2f"),
                    "currency": "USD",
                    "count": row.reservation_count
                }

            # No reservations found for this property
            return {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "total": "0.00",
                "currency": "USD",
                "count": 0
            }

    except PropertyNotFoundError:
        raise
    except Exception as error:
        logger.exception(
            "Revenue query failed for tenant=%s property=%s",
            tenant_id,
            property_id,
        )
        raise RevenueServiceError(
            "Revenue data could not be retrieved"
        ) from error
