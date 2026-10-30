from __future__ import annotations

from collections.abc import Mapping, Iterable


class PowerBudgetTracker:
    """Deprecated compatibility helper.

    Available Power is intentionally the configured source entity in the current
    Energy Dispenser model. This class is kept only so older imports do not break.
    """

    def __init__(self) -> None:
        self._available_power = 0.0

    def reset(self) -> None:
        self._available_power = 0.0

    def update(self, raw_available_power: float, effective_controlled_power: float = 0.0) -> float:
        self._available_power = float(raw_available_power)
        return self._available_power

    @property
    def available_power(self) -> float:
        return self._available_power


def calculate_available_power(
    raw_available_power: float,
    reserved_allocations: Mapping[str, float] | Iterable[float] | None = None,
) -> float:
    """Return the configured source value unchanged.

    The optional second argument remains only for source compatibility with
    earlier releases; allocations are not added to Available Power.
    """
    return float(raw_available_power)
