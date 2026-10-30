from __future__ import annotations

from math import isfinite


_WATT_FACTORS: dict[str | None, float] = {
    None: 1.0,
    "": 1.0,
    "W": 1.0,
    "kW": 1_000.0,
    "MW": 1_000_000.0,
    "mW": 0.001,
}


def power_to_watts(value: float | str, unit: str | None) -> float:
    """Convert a finite power value to watts.

    A missing unit is treated as watts for input_number entities and backward
    compatibility. Units are case-sensitive because mW and MW are different.
    """
    normalized_unit = unit.strip() if isinstance(unit, str) else None
    if normalized_unit not in _WATT_FACTORS:
        raise ValueError(f"Unsupported power unit: {unit!r}")

    watts = float(value) * _WATT_FACTORS[normalized_unit]
    if not isfinite(watts):
        raise ValueError(f"Power value must be finite: {value!r}")
    return watts
