from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from energy_dispenser.const import EVENT_ALLOCATION
from energy_dispenser.dispenser import EnergyDispenser
from energy_dispenser.models import EnergyReport


@dataclass
class FakeState:
    state: str
    attributes: dict = field(default_factory=dict)


@dataclass
class FakeStates:
    values: dict[str, FakeState] = field(default_factory=dict)

    def get(self, entity_id: str) -> FakeState | None:
        return self.values.get(entity_id)


@dataclass
class FakeBus:
    events: list[tuple[str, dict]] = field(default_factory=list)

    def async_fire(self, event_type: str, data: dict) -> None:
        self.events.append((event_type, data))


@dataclass
class FakeHass:
    states: FakeStates
    bus: FakeBus = field(default_factory=FakeBus)


def configured_consumer(consumer_id: str) -> dict:
    return {
        "consumer_id": consumer_id,
        "enabled": True,
        "minimum_power": 100,
        "preferred_power": 500,
        "maximum_power": 1000,
        "urgency": 0.5,
        "surplus_value": 1.0,
        "allow_import": False,
    }


def test_unavailable_source_publishes_zero_budget() -> None:
    hass = FakeHass(FakeStates({"sensor.available": FakeState("1000")}))
    dispenser = EnergyDispenser(hass, "sensor.available")
    dispenser.set_configured_consumers([configured_consumer("heater")])

    asyncio.run(dispenser.async_distribute())
    assert dispenser.last_result.allocations["heater"] == 1000

    hass.states.values["sensor.available"].state = "unavailable"
    asyncio.run(dispenser.async_distribute())

    assert dispenser.last_result.allocations["heater"] == 0
    allocation_events = [
        data for event_type, data in hass.bus.events if event_type == EVENT_ALLOCATION
    ]
    assert allocation_events[-1]["consumer_id"] == "heater"
    assert allocation_events[-1]["allocated_power"] == 0


def test_inactive_report_suppresses_configured_consumer_until_timeout(monkeypatch) -> None:
    hass = FakeHass(FakeStates({"sensor.available": FakeState("1000")}))
    dispenser = EnergyDispenser(hass, "sensor.available")
    dispenser.set_configured_consumers([configured_consumer("heater")])
    dispenser.reports["heater"] = EnergyReport(
        consumer_id="heater",
        state="inactive",
        report_timeout=15,
        updated_at=100,
    )

    monkeypatch.setattr("energy_dispenser.dispenser.monotonic", lambda: 105)
    asyncio.run(dispenser.async_distribute())

    assert "heater" in dispenser.reports
    assert dispenser.last_result.allocations == {}
    assert dispenser.budget_for_consumer("heater") is None

    monkeypatch.setattr("energy_dispenser.dispenser.monotonic", lambda: 116)
    asyncio.run(dispenser.async_distribute())

    assert "heater" not in dispenser.reports
    assert dispenser.last_result.allocations["heater"] == 1000
    assert dispenser.budget_for_consumer("heater") == 1000


def test_active_request_without_allocation_has_zero_budget() -> None:
    hass = FakeHass(FakeStates({"sensor.available": FakeState("50")}))
    dispenser = EnergyDispenser(hass, "sensor.available")
    dispenser.set_configured_consumers([configured_consumer("heater")])

    asyncio.run(dispenser.async_distribute())

    assert dispenser.request_is_active("heater")
    assert dispenser.budget_for_consumer("heater") == 0


def test_consumer_count_includes_only_active_requests(monkeypatch) -> None:
    hass = FakeHass(FakeStates({"sensor.available": FakeState("1000")}))
    dispenser = EnergyDispenser(hass, "sensor.available")
    dispenser.set_configured_consumers([configured_consumer("manual_heater")])
    dispenser.reports = {
        "automated_active": EnergyReport(
            consumer_id="automated_active",
            state="active",
            updated_at=100,
        ),
        "automated_inactive": EnergyReport(
            consumer_id="automated_inactive",
            state="inactive",
            updated_at=100,
        ),
    }
    monkeypatch.setattr("energy_dispenser.dispenser.monotonic", lambda: 105)

    assert dispenser.active_request_count() == 2


def test_available_source_is_converted_from_kw_to_watts() -> None:
    hass = FakeHass(
        FakeStates(
            {
                "sensor.available": FakeState(
                    "1.5",
                    {"unit_of_measurement": "kW"},
                )
            }
        )
    )
    dispenser = EnergyDispenser(hass, "sensor.available")
    dispenser.set_configured_consumers([configured_consumer("heater")])

    asyncio.run(dispenser.async_distribute())

    assert dispenser.last_result.available_power == 1500
    assert dispenser.last_result.allocations["heater"] == 1000
    assert dispenser.last_result.unallocated_power == 500


def test_configured_actual_power_entity_is_converted_from_kw() -> None:
    hass = FakeHass(
        FakeStates(
            {
                "sensor.available": FakeState("1000"),
                "sensor.heater_power": FakeState(
                    "1.2",
                    {"unit_of_measurement": "kW"},
                ),
            }
        )
    )
    dispenser = EnergyDispenser(hass, "sensor.available")
    consumer = configured_consumer("heater")
    consumer["actual_power_entity"] = "sensor.heater_power"
    dispenser.set_configured_consumers([consumer])

    assert dispenser.actual_power_for_consumer("heater") == 1200


def test_unsupported_source_unit_fails_closed() -> None:
    hass = FakeHass(
        FakeStates(
            {
                "sensor.available": FakeState(
                    "230",
                    {"unit_of_measurement": "V"},
                )
            }
        )
    )
    dispenser = EnergyDispenser(hass, "sensor.available")
    dispenser.set_configured_consumers([configured_consumer("heater")])

    asyncio.run(dispenser.async_distribute())

    assert dispenser.last_result.allocations["heater"] == 0


def test_invalid_automated_report_is_rejected() -> None:
    hass = FakeHass(FakeStates({"sensor.available": FakeState("1000")}))
    dispenser = EnergyDispenser(hass, "sensor.available")

    dispenser._accept_report(
        {
            "consumer_id": "invalid",
            "minimum_power": 1000,
            "preferred_power": 500,
            "maximum_power": 2000,
        }
    )

    assert "invalid" not in dispenser.reports


def test_invalid_automated_report_does_not_replace_last_valid_report() -> None:
    hass = FakeHass(FakeStates({"sensor.available": FakeState("1000")}))
    dispenser = EnergyDispenser(hass, "sensor.available")
    valid_report = EnergyReport(
        consumer_id="ev",
        minimum_power=100,
        preferred_power=500,
        maximum_power=1000,
    )
    dispenser.reports["ev"] = valid_report
    dispenser._accept_report(
        {
            "consumer_id": "ev",
            "minimum_power": 1000,
            "preferred_power": 500,
            "maximum_power": 2000,
        }
    )

    assert dispenser.reports["ev"] is valid_report
