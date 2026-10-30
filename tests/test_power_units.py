import pytest

from energy_dispenser.power_units import power_to_watts


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        (1200, "W", 1200),
        (1.216, "kW", 1216),
        (0.002, "MW", 2000),
        (500, "mW", 0.5),
        (750, None, 750),
        (750, "", 750),
    ],
)
def test_power_to_watts(value, unit, expected) -> None:
    assert power_to_watts(value, unit) == pytest.approx(expected)


def test_power_to_watts_rejects_unsupported_unit() -> None:
    with pytest.raises(ValueError, match="Unsupported power unit"):
        power_to_watts(230, "V")
