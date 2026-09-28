"""Tenant-scoped revenue reporting queries."""

from decimal import Decimal
from typing import Any

from sqlalchemy import text

from app.core.database_pool import db_pool
from app.services.revenue_reporting import format_money, month_bounds_utc


class PropertyNotFoundError(LookupError):
    """Raised when a property is not available to the current tenant."""


async def list_tenant_properties(tenant_id: str) -> list[dict[str, str]]:
    """Return only the properties owned by the authenticated tenant."""
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
        return [dict(row) for row in result.mappings().all()]


async def get_tenant_property(property_id: str, tenant_id: str) -> dict[str, str]:
    """Resolve a property only when it belongs to the current tenant."""
    await db_pool.initialize()
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
        row = result.mappings().one_or_none()

    if row is None:
        # Return the same response for an unknown property and a different
        # tenant's property so ownership information is not disclosed.
        raise PropertyNotFoundError("Property was not found for this tenant")

    return dict(row)


async def calculate_monthly_revenue(
    property_id: str,
    tenant_id: str,
    month: int,
    year: int,
    *,
    property_timezone: str | None = None,
) -> dict[str, Any]:
    """Calculate one property's revenue for a property-local calendar month."""
    if property_timezone is None:
        property = await get_tenant_property(property_id, tenant_id)
        property_timezone = property["timezone"]

    start_at, end_at = month_bounds_utc(year, month, property_timezone)
    await db_pool.initialize()

    async with db_pool.get_session() as session:
        result = await session.execute(
            text(
                """
                SELECT
                    COALESCE(SUM(total_amount), 0) AS total_revenue,
                    COUNT(*) AS reservation_count
                FROM reservations
                WHERE property_id = :property_id
                  AND tenant_id = :tenant_id
                  AND check_in_date >= :start_at
                  AND check_in_date < :end_at
                """
            ),
            {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "start_at": start_at,
                "end_at": end_at,
            },
        )
        row = result.mappings().one()

    total = Decimal(str(row["total_revenue"]))
    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": format_money(total),
        "currency": "USD",
        "count": int(row["reservation_count"] or 0),
        "year": year,
        "month": month,
    }
