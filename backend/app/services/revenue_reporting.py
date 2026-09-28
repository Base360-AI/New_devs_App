"""Pure helpers shared by tenant-scoped revenue reporting."""

from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

MONEY_QUANTUM = Decimal("0.01")


def month_bounds_utc(year: int, month: int, property_timezone: str) -> tuple[datetime, datetime]:
    """Build a property's local calendar-month range as UTC timestamps."""
    zone = ZoneInfo(property_timezone)
    start_local = datetime(year, month, 1, tzinfo=zone)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, tzinfo=zone)
    else:
        end_local = datetime(year, month + 1, 1, tzinfo=zone)

    return (
        start_local.astimezone(timezone.utc),
        end_local.astimezone(timezone.utc),
    )


def format_money(amount: Decimal) -> str:
    """Round a completed aggregate once and serialize it exactly to cents."""
    return format(amount.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP), ".2f")


def revenue_cache_key(tenant_id: str, property_id: str, year: int, month: int) -> str:
    """Include all response-affecting dimensions in a revenue cache key."""
    return f"revenue:{tenant_id}:{property_id}:{year:04d}-{month:02d}"
