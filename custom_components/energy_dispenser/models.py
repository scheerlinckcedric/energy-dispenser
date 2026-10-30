from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic

from .validation import validate_request_contract


@dataclass(slots=True)
class EnergyReport:
    consumer_id: str
    state: str = "active"
    minimum_power: float = 0.0
    preferred_power: float = 0.0
    maximum_power: float = 0.0
    urgency: float = 0.0
    surplus_value: float = 0.0
    actual_power: float = 0.0
    settling_time: float = 10.0
    minimum_claim_time: float = 20.0
    report_timeout: float = 15.0
    allow_import: bool = True
    updated_at: float = field(default_factory=monotonic)

    def __post_init__(self) -> None:
        self.state = str(self.state).lower().strip() or "active"
        self.minimum_power = float(self.minimum_power)
        self.preferred_power = float(self.preferred_power)
        self.maximum_power = float(self.maximum_power)
        self.urgency = float(self.urgency)
        self.surplus_value = float(self.surplus_value)
        self.actual_power = float(self.actual_power)
        self.settling_time = float(self.settling_time)
        self.minimum_claim_time = float(self.minimum_claim_time)
        self.report_timeout = float(self.report_timeout)
        validate_request_contract(
            minimum_power=self.minimum_power,
            preferred_power=self.preferred_power,
            maximum_power=self.maximum_power,
            urgency=self.urgency,
            surplus_value=self.surplus_value,
            actual_power=self.actual_power,
            settling_time=self.settling_time,
            minimum_claim_time=self.minimum_claim_time,
            report_timeout=self.report_timeout,
        )


@dataclass(slots=True)
class Claim:
    consumer_id: str
    watts: float = 0.0
    started_at: float = field(default_factory=monotonic)
    settling_until: float = 0.0
    settling_ceiling: float | None = None


@dataclass(slots=True)
class DispenserResult:
    available_power: float
    allocations: dict[str, float]
    unallocated_power: float
    timestamp: float = field(default_factory=monotonic)
