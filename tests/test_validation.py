import math

import pytest

from energy_dispenser.validation import RequestValidationError, validate_request_contract


def valid_contract(**overrides) -> dict:
    values = {
        "minimum_power": 100,
        "preferred_power": 500,
        "maximum_power": 1000,
        "urgency": 0.5,
        "surplus_value": 0.8,
        "actual_power": 250,
        "settling_time": 10,
        "minimum_claim_time": 20,
        "report_timeout": 15,
    }
    values.update(overrides)
    return values


def test_valid_request_contract_is_accepted() -> None:
    validate_request_contract(**valid_contract())


@pytest.mark.parametrize(
    "overrides",
    [
        {"minimum_power": -1},
        {"preferred_power": -1},
        {"maximum_power": -1},
        {"actual_power": -1},
    ],
)
def test_negative_power_is_rejected(overrides) -> None:
    with pytest.raises(RequestValidationError, match="non-negative"):
        validate_request_contract(**valid_contract(**overrides))


@pytest.mark.parametrize(
    "overrides",
    [
        {"minimum_power": 600, "preferred_power": 500},
        {"preferred_power": 1200, "maximum_power": 1000},
    ],
)
def test_invalid_power_order_is_rejected(overrides) -> None:
    with pytest.raises(RequestValidationError, match="minimum_power <= preferred_power <= maximum_power"):
        validate_request_contract(**valid_contract(**overrides))


@pytest.mark.parametrize(
    "overrides",
    [
        {"urgency": -0.1},
        {"urgency": 1.1},
        {"surplus_value": -0.1},
        {"surplus_value": 1.1},
    ],
)
def test_normalized_percentages_outside_zero_and_one_are_rejected(overrides) -> None:
    with pytest.raises(RequestValidationError, match="between 0 and 1"):
        validate_request_contract(**valid_contract(**overrides))


@pytest.mark.parametrize(
    "overrides",
    [
        {"settling_time": -1},
        {"minimum_claim_time": -1},
        {"report_timeout": 0},
    ],
)
def test_invalid_timing_is_rejected(overrides) -> None:
    with pytest.raises(RequestValidationError):
        validate_request_contract(**valid_contract(**overrides))


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_values_are_rejected(value) -> None:
    with pytest.raises(RequestValidationError, match="finite"):
        validate_request_contract(**valid_contract(maximum_power=value))
