from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any
from zoneinfo import ZoneInfo

MONEY_QUANTUM = Decimal("0.01")


class DatabaseUnavailableError(RuntimeError):
    """Raised when revenue cannot be computed from the live database."""


def _quantize_money(amount: Decimal) -> Decimal:
    return amount.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _month_bounds_utc(year: int, month: int, timezone_name: str) -> tuple[datetime, datetime]:
    tz = ZoneInfo(timezone_name or "UTC")
    start_local = datetime(year, month, 1, tzinfo=tz)
    if month < 12:
        end_local = datetime(year, month + 1, 1, tzinfo=tz)
    else:
        end_local = datetime(year + 1, 1, 1, tzinfo=tz)
    return start_local.astimezone(ZoneInfo("UTC")), end_local.astimezone(ZoneInfo("UTC"))


async def _fetch_property_timezone(session, property_id: str, tenant_id: str) -> str:
    from sqlalchemy import text

    result = await session.execute(
        text("""
            SELECT timezone
            FROM properties
            WHERE id = :property_id AND tenant_id = :tenant_id
        """),
        {"property_id": property_id, "tenant_id": tenant_id},
    )
    row = result.fetchone()
    return row.timezone if row and row.timezone else "UTC"


async def _open_session():
    from app.core.database_pool import db_pool

    try:
        await db_pool.initialize()
    except Exception as e:
        raise DatabaseUnavailableError(f"Database pool initialization failed: {e}") from e

    if not db_pool.session_factory:
        raise DatabaseUnavailableError("Database pool not available")

    return db_pool.get_session()


async def calculate_monthly_revenue(property_id: str, month: int, year: int, tenant_id: str,db_session=None,) -> Decimal:
    """
    Calculates revenue for a specific month in the property's local timezone.
    """
    session = db_session
    owns_session = session is None

    try:
        if session is None:
            session = await _open_session()

        timezone_name = await _fetch_property_timezone(session, property_id, tenant_id)
        start_utc, end_utc = _month_bounds_utc(year, month, timezone_name)

        from sqlalchemy import text

        result = await session.execute(
            text("""
                SELECT COALESCE(SUM(total_amount), 0) as total
                FROM reservations
                WHERE property_id = :property_id
                AND tenant_id = :tenant_id
                AND check_in_date >= :start_utc
                AND check_in_date < :end_utc
            """),
            {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "start_utc": start_utc,
                "end_utc": end_utc,
            },
        )
        row = result.fetchone()
        total = Decimal(str(row.total)) if row else Decimal("0")
        return _quantize_money(total)

    except DatabaseUnavailableError:
        raise
    except Exception as e:
        raise DatabaseUnavailableError(
            f"Monthly revenue query failed for {property_id} "
            f"(tenant: {tenant_id}, {year}-{month:02d}): {e}"
        ) from e

    finally:
        if owns_session and session is not None:
            await session.close()


async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    session = None
    try:
        session = await _open_session()
        from sqlalchemy import text

        query = text("""
            SELECT
                property_id,
                SUM(total_amount) as total_revenue,
                COUNT(*) as reservation_count
            FROM reservations
            WHERE property_id = :property_id AND tenant_id = :tenant_id
            GROUP BY property_id
        """)

        result = await session.execute(query, {
            "property_id": property_id,
            "tenant_id": tenant_id,
        })
        row = result.fetchone()

        if row:
            total_revenue = _quantize_money(Decimal(str(row.total_revenue)))
            return {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "total": str(total_revenue),
                "currency": "USD",
                "count": row.reservation_count,
            }

        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": "0.00",
            "currency": "USD",
            "count": 0,
        }

    except DatabaseUnavailableError:
        raise
    except Exception as e:
        raise DatabaseUnavailableError(
            f"Revenue query failed for {property_id} (tenant: {tenant_id}): {e}"
        ) from e

    finally:
        if session is not None:
            await session.close()
