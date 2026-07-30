"""Regression tests for the three revenue dashboard defects.

These cover the pure logic (period boundaries, cache keying, rounding) and so
run without a database or Redis. End-to-end checks against the seeded data live
in scripts/verify_fixes.sh.
"""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

import pytest

from app.services.cache import _cache_key
from app.services.reservations import month_bounds_utc


class TestMonthBoundsAreLocalToTheProperty:
    def test_paris_month_starts_before_utc_midnight(self):
        start, end = month_bounds_utc(3, 2024, "Europe/Paris")

        # March in Paris (UTC+1) begins at 23:00 UTC on 29 February.
        assert start == datetime(2024, 2, 29, 23, 0, tzinfo=timezone.utc)
        assert end == datetime(2024, 3, 31, 22, 0, tzinfo=timezone.utc)

    def test_new_york_month_starts_after_utc_midnight(self):
        start, end = month_bounds_utc(3, 2024, "America/New_York")

        # March in New York (UTC-5) begins at 05:00 UTC on 1 March.
        assert start == datetime(2024, 3, 1, 5, 0, tzinfo=timezone.utc)
        assert end == datetime(2024, 4, 1, 4, 0, tzinfo=timezone.utc)

    def test_reservation_just_after_local_midnight_falls_in_march(self):
        """The booking behind Sunset Properties' March discrepancy.

        Checking in at 2024-02-29 23:30 UTC is 00:30 on 1 March in Paris, so it
        belongs to March. Naive UTC bounds pushed it into February.
        """
        check_in = datetime(2024, 2, 29, 23, 30, tzinfo=timezone.utc)

        march_start, march_end = month_bounds_utc(3, 2024, "Europe/Paris")
        february_start, february_end = month_bounds_utc(2, 2024, "Europe/Paris")

        assert march_start <= check_in < march_end
        assert not (february_start <= check_in < february_end)

    def test_december_rolls_over_to_next_year(self):
        start, end = month_bounds_utc(12, 2024, "Europe/Paris")

        assert start == datetime(2024, 11, 30, 23, 0, tzinfo=timezone.utc)
        assert end == datetime(2024, 12, 31, 23, 0, tzinfo=timezone.utc)

    def test_dst_transition_month_uses_correct_offsets(self):
        """Paris switches to UTC+2 on 31 March 2024, so the month's two ends
        carry different offsets."""
        start, end = month_bounds_utc(3, 2024, "Europe/Paris")

        assert start.hour == 23  # UTC+1 at the start of the month
        assert end.hour == 22    # UTC+2 by the end of it


class TestCacheKeysAreTenantScoped:
    def test_same_property_id_in_two_tenants_uses_distinct_keys(self):
        """prop-001 exists for both clients; one key for both leaked revenue."""
        key_a = _cache_key("prop-001", "tenant-a", None, None)
        key_b = _cache_key("prop-001", "tenant-b", None, None)

        assert key_a != key_b
        assert "tenant-a" in key_a
        assert "tenant-b" in key_b

    def test_periods_do_not_share_a_key(self):
        all_time = _cache_key("prop-001", "tenant-a", None, None)
        march = _cache_key("prop-001", "tenant-a", 3, 2024)
        april = _cache_key("prop-001", "tenant-a", 4, 2024)

        assert len({all_time, march, april}) == 3

    def test_month_is_zero_padded_so_keys_are_unambiguous(self):
        assert _cache_key("prop-001", "tenant-a", 3, 2024).endswith("2024-03")


class TestMonetaryPrecision:
    def test_sub_cent_amounts_sum_exactly_in_decimal(self):
        amounts = [Decimal("333.333"), Decimal("333.333"), Decimal("333.334")]

        assert sum(amounts) == Decimal("1000.000")
        assert sum(amounts).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == Decimal("1000.00")

    def test_rounding_each_amount_first_would_lose_a_cent(self):
        """Why the total is rounded once, at the very end."""
        amounts = [Decimal("333.333"), Decimal("333.333"), Decimal("333.334")]
        rounded_first = sum(a.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) for a in amounts)

        assert rounded_first == Decimal("999.99")  # a cent short of the truth

    @pytest.mark.parametrize(
        "amount,decimal_result,float_result",
        [
            ("333.335", "333.34", 333.33),
            ("2.675", "2.68", 2.67),
            ("1.005", "1.01", 1.0),
        ],
    )
    def test_float_round_trip_drifts_where_decimal_does_not(self, amount, decimal_result, float_result):
        """The old endpoint did float(total), then the UI did Math.round(x*100)/100.

        Half-way amounts are not representable in binary, so they land a cent
        below the correct figure - the finance team's "slightly off by a few
        cents here and there".
        """
        exact = Decimal(amount)

        assert exact.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) == Decimal(decimal_result)
        assert round(float(exact), 2) == float_result

    def test_decimal_is_built_from_string_not_float(self):
        assert Decimal(str(0.1)) == Decimal("0.1")
        assert Decimal(0.1) != Decimal("0.1")


@pytest.mark.parametrize(
    "tz,month,year",
    [("Europe/Paris", 1, 2024), ("America/New_York", 12, 2023), ("UTC", 6, 2025)],
)
def test_bounds_are_always_utc_aware_and_ordered(tz, month, year):
    start, end = month_bounds_utc(month, year, tz)

    assert start.tzinfo is not None and end.tzinfo is not None
    assert start < end
