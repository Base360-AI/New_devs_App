from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.core.database_pool import DatabasePool


CURRENCY_QUANTUM = Decimal("0.01")


def format_currency_total(value: Any) -> str:
    """Return an exact two-decimal currency value using commercial rounding."""
    amount = Decimal(str(value or 0))
    return format(amount.quantize(CURRENCY_QUANTUM, rounding=ROUND_HALF_UP), ".2f")


def report_period_utc(year: int, month: int, timezone_name: str) -> Tuple[datetime, datetime]:
    """Convert a property-local calendar month to an exclusive UTC range."""
    property_timezone = ZoneInfo(timezone_name)
    start_local = datetime(year, month, 1, tzinfo=property_timezone)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, tzinfo=property_timezone)
    else:
        end_local = datetime(year, month + 1, 1, tzinfo=property_timezone)

    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _empty_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": "0.00",
        "currency": "USD",
        "count": 0,
    }


async def calculate_total_revenue(
    property_id: str,
    tenant_id: str,
    month: int | None = None,
    year: int | None = None,
) -> Dict[str, Any]:
    """Aggregate tenant-scoped revenue, optionally for a property-local month."""
    if (month is None) != (year is None):
        raise ValueError("month and year must be provided together")

    db_pool = DatabasePool()
    try:
        await db_pool.initialize()
        async with db_pool.get_session() as session:
            property_result = await session.execute(
                text(
                    """
                    SELECT timezone
                    FROM properties
                    WHERE id = :property_id AND tenant_id = :tenant_id
                    """
                ),
                {"property_id": property_id, "tenant_id": tenant_id},
            )
            property_row = property_result.fetchone()
            if property_row is None:
                return _empty_revenue(property_id, tenant_id)

            parameters: Dict[str, Any] = {
                "property_id": property_id,
                "tenant_id": tenant_id,
            }
            date_filter = ""
            if month is not None and year is not None:
                start_utc, end_utc = report_period_utc(year, month, property_row.timezone)
                parameters.update({"start_utc": start_utc, "end_utc": end_utc})
                date_filter = """
                    AND check_in_date >= :start_utc
                    AND check_in_date < :end_utc
                """

            revenue_result = await session.execute(
                text(
                    f"""
                    SELECT
                        COALESCE(SUM(total_amount), 0) AS total_revenue,
                        COUNT(*) AS reservation_count
                    FROM reservations
                    WHERE property_id = :property_id
                      AND tenant_id = :tenant_id
                      {date_filter}
                    """
                ),
                parameters,
            )
            row = revenue_result.fetchone()

            return {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "total": format_currency_total(row.total_revenue),
                "currency": "USD",
                "count": row.reservation_count,
            }
    except Exception as exc:
        raise RuntimeError(
            f"Revenue calculation failed for property {property_id}"
        ) from exc
    finally:
        await db_pool.close()


async def list_tenant_properties(tenant_id: str) -> List[Dict[str, str]]:
    """List only properties owned by the authenticated tenant."""
    db_pool = DatabasePool()
    try:
        await db_pool.initialize()
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
            return [
                {"id": row.id, "name": row.name, "timezone": row.timezone}
                for row in result.fetchall()
            ]
    except Exception as exc:
        raise RuntimeError("Property lookup failed") from exc
    finally:
        await db_pool.close()
