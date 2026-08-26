"""
Unit tests for the revenue bug fixes. Pure functions only - no DB/Redis needed.

Run:  cd backend && python -m pytest -q
"""
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.services.cache import revenue_cache_key
from app.services.reservations import month_bounds, to_money


# --- Bug 1: cache key must be tenant-scoped -----------------------------------------

def test_cache_key_isolates_tenants_sharing_a_property_id():
    a = revenue_cache_key("tenant-a", "prop-001")
    b = revenue_cache_key("tenant-b", "prop-001")
    assert a != b
    assert "tenant-a" in a and "tenant-b" in b


def test_cache_key_isolates_periods():
    assert revenue_cache_key("tenant-a", "prop-001") != revenue_cache_key("tenant-a", "prop-001", 3, 2024)
    assert revenue_cache_key("tenant-a", "prop-001", 3, 2024) != revenue_cache_key("tenant-a", "prop-001", 4, 2024)


def test_cache_key_requires_tenant():
    with pytest.raises(ValueError):
        revenue_cache_key("", "prop-001")


# --- Bug 4: money is rounded once, half-up, never via float ---------------------------

def test_sum_then_round_does_not_drift():
    rows = [Decimal("333.333"), Decimal("333.333"), Decimal("333.334")]
    assert to_money(sum(rows)) == Decimal("1000.00")
    # The buggy behaviour (round each row first) loses a cent:
    assert sum(to_money(r) for r in rows) == Decimal("999.99")


def test_round_half_up_not_bankers():
    assert to_money(Decimal("4975.525")) == Decimal("4975.53")
    assert to_money(Decimal("0.005")) == Decimal("0.01")


def test_seed_totals():
    tenant_a_prop_001 = [Decimal("1250.000"), Decimal("333.333"), Decimal("333.333"), Decimal("333.334")]
    assert to_money(sum(tenant_a_prop_001)) == Decimal("2250.00")


# --- Bug 3: month boundaries live in the property's timezone -------------------------

def test_month_bounds_are_half_open():
    start, end = month_bounds(2024, 3)
    assert start == datetime(2024, 3, 1)
    assert end == datetime(2024, 4, 1)
    assert month_bounds(2024, 12)[1] == datetime(2025, 1, 1)


def test_month_bounds_rejects_bad_month():
    with pytest.raises(ValueError):
        month_bounds(2024, 13)


def test_feb_29_2330_utc_is_march_in_paris_but_february_in_new_york():
    """Seed row res-tz-1: the check-in that caused Sunset's 'March mismatch'."""
    check_in = datetime(2024, 2, 29, 23, 30, tzinfo=timezone.utc)
    march_start, april_start = month_bounds(2024, 3)

    paris_local = check_in.astimezone(ZoneInfo("Europe/Paris")).replace(tzinfo=None)
    assert march_start <= paris_local < april_start  # counted in March for a Paris property

    ny_local = check_in.astimezone(ZoneInfo("America/New_York")).replace(tzinfo=None)
    assert ny_local < march_start  # would be February for a New York property

    naive_utc = check_in.replace(tzinfo=None)
    assert naive_utc < march_start  # the old naive-UTC logic put it in February

