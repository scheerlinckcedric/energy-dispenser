from energy_dispenser.allocator import EnergyAllocator
from energy_dispenser.models import EnergyReport


def report(
    consumer_id: str,
    *,
    minimum: float,
    preferred: float,
    maximum: float,
    urgency: float = 0.0,
    surplus_value: float = 1.0,
    allow_import: bool = False,
) -> EnergyReport:
    return EnergyReport(
        consumer_id=consumer_id,
        minimum_power=minimum,
        preferred_power=preferred,
        maximum_power=maximum,
        urgency=urgency,
        surplus_value=surplus_value,
        allow_import=allow_import,
    )


def test_hard_minimum_blocks_partial_start() -> None:
    result = EnergyAllocator().allocate(1300, [report("ev", minimum=1400, preferred=3000, maximum=4600)])
    assert result.allocations["ev"] == 0


def test_hard_maximum_is_respected() -> None:
    result = EnergyAllocator().allocate(7064, [report("ev", minimum=10, preferred=40, maximum=85, surplus_value=1.0)])
    assert result.allocations["ev"] == 85
    assert result.unallocated_power == 6979


def test_two_equal_consumers_share_surplus() -> None:
    consumers = [
        report("a", minimum=1500, preferred=3000, maximum=5000),
        report("b", minimum=1500, preferred=3000, maximum=5000),
    ]
    result = EnergyAllocator().allocate(6500, consumers)
    assert result.allocations == {"a": 3250.0, "b": 3250.0}


def test_import_only_allowed_consumer_receives_import_budget() -> None:
    ev = report("ev", minimum=1400, preferred=3000, maximum=4600, allow_import=True)
    lamp = report("lamp", minimum=30, preferred=30, maximum=30, allow_import=False)
    result = EnergyAllocator().allocate(-1450, [ev, lamp])
    assert result.allocations["ev"] == 1450
    assert result.allocations["lamp"] == 0


def test_import_below_minimum_gets_nothing() -> None:
    ev = report("ev", minimum=1400, preferred=3000, maximum=4600, allow_import=True)
    result = EnergyAllocator().allocate(-500, [ev])
    assert result.allocations["ev"] == 0


def test_allow_import_consumer_can_reserve_minimum_above_available_surplus() -> None:
    ev = report("ev", minimum=1320, preferred=3000, maximum=4600, allow_import=True)
    lamp = report("lamp", minimum=30, preferred=30, maximum=30, allow_import=False)
    result = EnergyAllocator().allocate(896, [ev, lamp])
    assert result.allocations["ev"] == 1320
    assert result.allocations["lamp"] == 0
    assert result.unallocated_power == 0


def test_non_import_consumer_does_not_consume_grid_when_minimum_is_unreachable() -> None:
    ev = report("ev", minimum=1320, preferred=3000, maximum=4600, allow_import=False)
    lamp = report("lamp", minimum=30, preferred=30, maximum=30, allow_import=False)
    result = EnergyAllocator().allocate(896, [ev, lamp])
    assert result.allocations["ev"] == 0
    assert result.allocations["lamp"] == 30
    assert result.unallocated_power == 866


def test_import_consumer_gets_complete_minimum_when_surplus_is_below_allocation_step() -> None:
    ev = report("ev", minimum=1320, preferred=3000, maximum=4600, allow_import=True)
    result = EnergyAllocator().allocate(30, [ev])
    assert result.allocations["ev"] == 1320
    assert result.unallocated_power == 0
