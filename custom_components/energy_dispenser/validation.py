from __future__ import annotations

import math


class RequestValidationError(ValueError):
    """A request violates the generic Energy Dispenser contract."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_request_contract(
    *,
    minimum_power: float,
    preferred_power: float,
    maximum_power: float,
    urgency: float,
    surplus_value: float,
    actual_power: float,
    settling_time: float,
    minimum_claim_time: float,
    report_timeout: float,
) -> None:
    """Validate the numeric, device-independent request contract."""
    values = {
        "minimum_power": minimum_power,
        "preferred_power": preferred_power,
        "maximum_power": maximum_power,
        "urgency": urgency,
        "surplus_value": surplus_value,
        "actual_power": actual_power,
        "settling_time": settling_time,
        "minimum_claim_time": minimum_claim_time,
        "report_timeout": report_timeout,
    }
    if any(not math.isfinite(value) for value in values.values()):
        raise RequestValidationError(
            "non_finite_value",
            "All numeric request values must be finite.",
        )

    power_values = (minimum_power, preferred_power, maximum_power, actual_power)
    if any(value < 0 for value in power_values):
        raise RequestValidationError(
            "negative_power",
            "Power values must be non-negative.",
        )

    if not minimum_power <= preferred_power <= maximum_power:
        raise RequestValidationError(
            "invalid_power_order",
            "Power values must satisfy minimum_power <= preferred_power <= maximum_power.",
        )

    if not 0 <= urgency <= 1 or not 0 <= surplus_value <= 1:
        raise RequestValidationError(
            "normalized_value_out_of_range",
            "Urgency and surplus value must be between 0 and 1.",
        )

    if settling_time < 0 or minimum_claim_time < 0:
        raise RequestValidationError(
            "negative_timing",
            "Settling time and minimum claim time must be non-negative.",
        )

    if report_timeout < 1:
        raise RequestValidationError(
            "invalid_report_timeout",
            "Report timeout must be at least 1 second.",
        )
