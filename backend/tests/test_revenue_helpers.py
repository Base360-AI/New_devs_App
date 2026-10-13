"""Unit tests for revenue helpers (no database needed).

Run from backend/: uv run --no-project --with pytest pytest -q -p no:cacheprovider
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.services.reservations import month_bounds, to_money


def test_total_is_rounded_once_not_per_booking():
    bookings = [Decimal("333.333"), Decimal("333.333"), Decimal("333.334")]
    assert to_money(sum(bookings)) == "1000.00"
    # Rounding each booking first would drift by a cent
    assert sum(Decimal(to_money(b)) for b in bookings) == Decimal("999.99")


def test_to_money_rounds_half_up_and_handles_empty():
    assert to_money(Decimal("0.005")) == "0.01"
    assert to_money(None) == "0.00"


def test_month_bounds_use_property_timezone():
    start, end = month_bounds(2024, 3, "Europe/Paris")
    # 2024-02-29 23:30 UTC is 1 March 00:30 in Paris, so it belongs to March
    check_in = datetime(2024, 2, 29, 23, 30, tzinfo=timezone.utc)
    assert start <= check_in < end
    # Absolute length (what Postgres compares) is 31 days minus the DST hour
    utc = timezone.utc
    assert end.astimezone(utc) - start.astimezone(utc) == timedelta(days=31, hours=-1)


def test_month_bounds_december_rolls_over_to_next_year():
    start, end = month_bounds(2024, 12, "America/New_York")
    assert (start.year, start.month, end.year, end.month) == (2024, 12, 2025, 1)
