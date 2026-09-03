from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from inspect import isawaitable
from typing import Any, Dict, Optional


CURRENCY_QUANTUM = Decimal("0.01")


def round_currency(amount: Decimal) -> Decimal:
    """Round an already-aggregated monetary amount to cents."""
    return amount.quantize(CURRENCY_QUANTUM, rounding=ROUND_HALF_UP)


async def calculate_monthly_revenue(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> Dict[str, Any]:
    """Aggregate revenue for a single UTC calendar month.

    If no period is requested, the latest month containing a reservation for
    the tenant and property is selected. Property-local timezone handling is a
    separate concern; this query deliberately uses UTC boundaries.
    """
    if (month is None) != (year is None):
        raise ValueError("month and year must be provided together")
    if month is not None and not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")
    if year is not None and not 2000 <= year <= 2100:
        raise ValueError("year must be between 2000 and 2100")

    try:
        from sqlalchemy import text

        from app.core.database_pool import DatabasePool

        db_pool = DatabasePool()
        await db_pool.initialize()

        if not db_pool.session_factory:
            raise RuntimeError("Database pool not available")

        session_context = db_pool.get_session()
        if isawaitable(session_context):
            session_context = await session_context

        async with session_context as session:
            if month is None and year is None:
                period_result = await session.execute(
                    text(
                        """
                        SELECT
                            CAST(EXTRACT(
                                YEAR FROM (check_in_date AT TIME ZONE 'UTC')
                            ) AS INTEGER) AS year,
                            CAST(EXTRACT(
                                MONTH FROM (check_in_date AT TIME ZONE 'UTC')
                            ) AS INTEGER) AS month
                        FROM reservations
                        WHERE property_id = :property_id
                          AND tenant_id = :tenant_id
                        ORDER BY check_in_date DESC
                        LIMIT 1
                        """
                    ),
                    {"property_id": property_id, "tenant_id": tenant_id},
                )
                period = period_result.fetchone()
                if not period:
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total": "0.00",
                        "currency": "USD",
                        "count": 0,
                        "month": None,
                        "year": None,
                    }

                month = int(period.month)
                year = int(period.year)

            start_date = datetime(year, month, 1, tzinfo=timezone.utc)
            if month == 12:
                end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
            else:
                end_date = datetime(year, month + 1, 1, tzinfo=timezone.utc)

            result = await session.execute(
                text(
                    """
                    SELECT
                        COALESCE(SUM(total_amount), 0) AS total_revenue,
                        COUNT(*) AS reservation_count
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

            precise_total = Decimal(str(row.total_revenue)) if row else Decimal("0")
            total_revenue = round_currency(precise_total)
            return {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "total": str(total_revenue),
                "currency": "USD",
                "count": row.reservation_count if row else 0,
                "month": month,
                "year": year,
            }

    except Exception as error:
        print(f"Database error for {property_id} (tenant: {tenant_id}): {error}")

        # Preserve the challenge-mode fallback; connection/error handling is
        # addressed independently from this monthly-query change.
        mock_data = {
            "prop-001": {"total": "1000.00", "count": 3},
            "prop-002": {"total": "4975.50", "count": 4},
            "prop-003": {"total": "6100.50", "count": 2},
            "prop-004": {"total": "1776.50", "count": 4},
            "prop-005": {"total": "3256.00", "count": 3},
        }
        mock_property_data = mock_data.get(
            property_id, {"total": "0.00", "count": 0}
        )

        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": mock_property_data["total"],
            "currency": "USD",
            "count": mock_property_data["count"],
            "month": month,
            "year": year,
        }
