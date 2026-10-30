import asyncio
from types import SimpleNamespace

from energy_dispenser.config_flow import (
    CONSUMERS_KEY,
    EnergyDispenserConfigFlow,
    _power_entity_selector,
)
from energy_dispenser.const import CONF_AVAILABLE_POWER_ENTITY


class _ConfigEntries:
    def __init__(self, entry):
        self._entry = entry

    def async_get_known_entry(self, entry_id):
        assert entry_id == self._entry.entry_id
        return self._entry


def test_options_flow_uses_home_assistant_injected_config_entry() -> None:
    entry = SimpleNamespace(
        entry_id="entry-1",
        data={CONF_AVAILABLE_POWER_ENTITY: "sensor.solar_surplus"},
        options={
            CONSUMERS_KEY: [
                {
                    "consumer_id": "boiler",
                    "name": "Boiler",
                    "minimum_power": 2000,
                    "preferred_power": 2000,
                    "maximum_power": 2000,
                }
            ]
        },
        runtime_data=None,
    )

    flow = EnergyDispenserConfigFlow.async_get_options_flow(entry)
    assert not hasattr(flow, "_consumers")

    flow.handler = entry.entry_id
    flow.hass = SimpleNamespace(
        config_entries=_ConfigEntries(entry),
        data={},
    )

    result = asyncio.run(flow.async_step_init())

    assert result["type"] == "menu"
    assert flow._available_power_entity == "sensor.solar_surplus"
    assert flow._consumers[0]["consumer_id"] == "boiler"


def test_power_entity_selector_uses_or_filters() -> None:
    entity_selector = _power_entity_selector()

    assert entity_selector.config == {
        "filter": [
            {"domain": "sensor", "device_class": "power"},
            {"domain": "input_number"},
        ]
    }
