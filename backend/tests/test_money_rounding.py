from decimal import Decimal

import pytest

from app.services.reservations import _to_cents


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2250.000", "2250.00"),
        ("999.999", "1000.00"),
        ("1776.505", "1776.51"),
        ("333.333", "333.33"),
        ("0.005", "0.01"),
        ("0.004", "0.00"),
        (Decimal("1000.000"), "1000.00"),
        (0, "0.00"),
        (None, "0.00"),
    ],
)
def test_to_cents_rounds_half_up_to_two_places(value, expected):
    result = _to_cents(value)
    assert isinstance(result, Decimal)
    assert str(result) == expected


def test_to_cents_avoids_float_rounding_error():
    # 2.675 has no exact binary float; float rounding gives 2.67.
    assert round(2.675, 2) == 2.67
    assert str(_to_cents("2.675")) == "2.68"


def test_sum_then_round_matches_seed_data():
    # The three seed reservations for prop-001 (tenant-a) in mid-March.
    amounts = [Decimal("333.333"), Decimal("333.333"), Decimal("333.334")]
    assert str(_to_cents(sum(amounts))) == "1000.00"
