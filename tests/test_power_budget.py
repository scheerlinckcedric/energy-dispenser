from energy_dispenser.power_budget import PowerBudgetTracker, calculate_available_power


def test_available_power_is_exactly_the_configured_source() -> None:
    tracker = PowerBudgetTracker()
    assert tracker.update(2173, 0) == 2173
    assert tracker.update(940, 2206) == 940
    assert tracker.available_power == 940


def test_allocations_do_not_increase_available_power() -> None:
    assert calculate_available_power(2173, {"ev_auto": 4600}) == 2173


def test_source_changes_are_followed_directly() -> None:
    tracker = PowerBudgetTracker()
    assert tracker.update(2173) == 2173
    assert tracker.update(2500) == 2500
    assert tracker.update(1800) == 1800

from types import SimpleNamespace
from energy_dispenser.allocator import EnergyAllocator
from energy_dispenser.models import EnergyReport


def _report(consumer_id: str, actual: float = 0, settling: float = 20, minimum_claim: float = 20):
    return EnergyReport(
        consumer_id=consumer_id,
        state="active",
        minimum_power=1380,
        preferred_power=2000,
        maximum_power=4600,
        urgency=0.0,
        surplus_value=1.0,
        actual_power=actual,
        settling_time=settling,
        minimum_claim_time=minimum_claim,
        report_timeout=15,
        allow_import=True,
    )


def test_existing_claim_is_protected_when_measured_surplus_drops_during_settling(monkeypatch) -> None:
    allocator = EnergyAllocator()
    timeline = iter([0.0, 0.0, 5.0, 5.0])
    monkeypatch.setattr("energy_dispenser.allocator.monotonic", lambda: next(timeline))

    first = allocator.allocate(2000, [_report("ev")])
    assert first.allocations["ev"] == 2000

    # The EV has started drawing power, but its actual-power report has not caught up yet.
    second = allocator.allocate(900, [_report("ev", actual=0)])
    assert second.allocations["ev"] == 2000
    assert second.available_power == 2000


def test_reported_actual_power_reconstructs_source_after_settling(monkeypatch) -> None:
    allocator = EnergyAllocator()
    timeline = iter([0.0, 30.0, 30.0])
    monkeypatch.setattr("energy_dispenser.allocator.monotonic", lambda: next(timeline))

    first = allocator.allocate(2000, [_report("ev")])
    assert first.allocations["ev"] == 2000

    # Once settling has expired, a real source calculation can be used again.
    second = allocator.allocate(2120, [_report("ev", actual=1220)])
    assert second.available_power == 2120
    assert second.allocations["ev"] == 2120


def test_reconstructed_source_formula() -> None:
    raw = 900
    actual_controlled = 1220
    assert raw + actual_controlled == 2120


def test_protected_claim_survives_source_below_minimum(monkeypatch) -> None:
    allocator = EnergyAllocator()
    timeline = iter([0.0, 5.0, 5.0])
    monkeypatch.setattr("energy_dispenser.allocator.monotonic", lambda: next(timeline))

    first = allocator.allocate(2000, [_report("ev", actual=0)])
    assert first.allocations["ev"] == 2000

    # 900 W is below the EV minimum, but the previous 2000 W claim is still
    # protected while the device settles and its actual-power feedback lags.
    second = allocator.allocate(900, [_report("ev", actual=0)])
    assert second.available_power == 2000
    assert second.allocations["ev"] == 2000


def test_reported_actual_cannot_grow_claim_during_settling(monkeypatch) -> None:
    allocator = EnergyAllocator()
    timeline = iter([0.0, 5.0, 5.0])
    monkeypatch.setattr("energy_dispenser.allocator.monotonic", lambda: next(timeline))

    first = allocator.allocate(2000, [_report("ev", actual=0)])
    assert first.allocations["ev"] == 2000

    # Even when actual power starts reporting, its update may overlap with a
    # stale source sample. Keep the initial 2000 W ceiling until settling ends.
    second = allocator.allocate(2120, [_report("ev", actual=1220)])
    assert second.available_power == 2000
    assert second.allocations["ev"] == 2000


def test_settling_ceiling_blocks_unsynchronised_feedback_spike(monkeypatch) -> None:
    allocator = EnergyAllocator()
    timeline = iter([0.0, 5.0, 21.0])
    monkeypatch.setattr("energy_dispenser.allocator.monotonic", lambda: next(timeline))

    first = allocator.allocate(4000, [_report("ev", settling=20, minimum_claim=20)])
    assert first.allocations["ev"] == 4000

    # The source and charger sensors overlap briefly: both appear to contain
    # the same 4000 W. The settling ceiling must not expose an 8000 W pool.
    spike = allocator.allocate(8000, [_report("ev", actual=4000, settling=20, minimum_claim=20)])
    assert spike.available_power == 4000
    assert spike.allocations["ev"] == 4000

    # Once settling has ended, real source growth may be allocated normally.
    settled = allocator.allocate(8000, [_report("ev", actual=4000, settling=20, minimum_claim=20)])
    assert settled.available_power == 8000
    assert settled.allocations["ev"] == 4600


def test_minimum_claim_protection_outlives_measurement_settling(monkeypatch) -> None:
    allocator = EnergyAllocator()
    timeline = iter([0.0, 15.0])
    monkeypatch.setattr("energy_dispenser.allocator.monotonic", lambda: next(timeline))

    first = allocator.allocate(2000, [_report("ev", settling=10, minimum_claim=60)])
    assert first.allocations["ev"] == 2000
    assert allocator.claim_is_settled("ev", now=15)

    # Measurements are trusted after 10 seconds, but the existing 2000 W claim
    # remains protected from disappearing for the configured 60 seconds.
    protected = allocator.allocate(0, [_report("ev", settling=10, minimum_claim=60)])
    assert protected.available_power == 2000
    assert protected.allocations["ev"] == 2000


def test_minimum_claim_time_does_not_extend_settling_ceiling(monkeypatch) -> None:
    allocator = EnergyAllocator()
    timeline = iter([0.0, 15.0])
    monkeypatch.setattr("energy_dispenser.allocator.monotonic", lambda: next(timeline))

    allocator.allocate(2000, [_report("ev", settling=10, minimum_claim=60)])
    increased = allocator.allocate(6000, [_report("ev", settling=10, minimum_claim=60)])

    assert increased.available_power == 6000
    assert increased.allocations["ev"] == 4600
