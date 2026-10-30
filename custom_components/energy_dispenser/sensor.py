from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory

from .const import EVENT_RESULT
from .dispenser import EnergyDispenser


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    dispenser: EnergyDispenser = entry.runtime_data
    added_budget_ids: set[str] = set()

    configured_consumers = [
        item
        for item in entry.options.get("consumers", [])
        if str(item.get("consumer_id", "")).strip()
    ]

    # Reconcile the entity registry on every platform setup. Config-flow
    # changes unload/reload the platform, but HA intentionally keeps entity
    # registry entries. Remove budget entities whose consumer no longer exists
    # so the sensor list reflects the current Energy Dispenser configuration.
    configured_ids = {str(item.get("consumer_id", "")).strip() for item in configured_consumers}
    reported_ids = {str(consumer_id).strip() for consumer_id in dispenser.reports}
    desired_ids = {consumer_id for consumer_id in configured_ids | reported_ids if consumer_id}
    registry = er.async_get(hass)
    budget_prefix = "energy_dispenser_budget_"
    actual_prefix = "energy_dispenser_actual_power_"
    for entity in list(registry.entities.values()):
        if (
            entity.config_entry_id == entry.entry_id
            and entity.domain == "sensor"
            and entity.unique_id.startswith(budget_prefix)
        ):
            consumer_id = entity.unique_id[len(budget_prefix):]
            if consumer_id not in desired_ids:
                registry.async_remove(entity.entity_id)
                continue

            # Migrate existing entities created from the display name, e.g.
            # sensor.budget_ev_charger -> sensor.budget_ev_auto.
            desired_entity_id = f"sensor.budget_{consumer_id}"
            if entity.entity_id != desired_entity_id:
                existing = registry.async_get(desired_entity_id)
                if existing is None or existing.entity_id == entity.entity_id:
                    try:
                        registry.async_update_entity(
                            entity.entity_id, new_entity_id=desired_entity_id
                        )
                    except ValueError:
                        # Leave the registry entry untouched if another entity
                        # already owns the desired entity_id.
                        pass

    for entity in list(registry.entities.values()):
        if (
            entity.config_entry_id == entry.entry_id
            and entity.domain == "sensor"
            and entity.unique_id.startswith(actual_prefix)
        ):
            consumer_id = entity.unique_id[len(actual_prefix):]
            if consumer_id not in desired_ids:
                registry.async_remove(entity.entity_id)
                continue
            desired_entity_id = f"sensor.actual_power_{consumer_id}"
            if entity.entity_id != desired_entity_id:
                existing = registry.async_get(desired_entity_id)
                if existing is None or existing.entity_id == entity.entity_id:
                    try:
                        registry.async_update_entity(
                            entity.entity_id, new_entity_id=desired_entity_id
                        )
                    except ValueError:
                        pass

    entities: list[SensorEntity] = [
        DispenserSensor(dispenser, "Available Power", "available_power", "W"),
        DispenserSensor(dispenser, "Unallocated Power", "unallocated_power", "W"),
        DispenserSensor(
            dispenser,
            "Consumer Count",
            "consumer_count",
            None,
            dispenser.configured_consumer_count,
        ),
    ]

    configured_names = {
        str(item.get("consumer_id", "")).strip(): (
            str(item.get("name", item.get("consumer_id", ""))).strip()
            or str(item.get("consumer_id", "")).strip()
        )
        for item in configured_consumers
        if str(item.get("consumer_id", "")).strip()
    }

    for consumer_id in sorted(desired_ids):
        entities.append(
            BudgetSensor(
                dispenser,
                consumer_id,
                configured_names.get(consumer_id, consumer_id),
            )
        )
        entities.append(
            ActualPowerSensor(
                dispenser,
                consumer_id,
                configured_names.get(consumer_id, consumer_id),
            )
        )
        added_budget_ids.add(consumer_id)

    async_add_entities(entities)

    @callback
    def _add_dynamic_budget(consumer_id: str) -> None:
        consumer_id = str(consumer_id).strip()
        if not consumer_id or consumer_id in added_budget_ids:
            return
        added_budget_ids.add(consumer_id)
        async_add_entities([
            BudgetSensor(dispenser, consumer_id, consumer_id),
            ActualPowerSensor(dispenser, consumer_id, consumer_id),
        ])

    dispenser.set_budget_entity_adder(_add_dynamic_budget)
    for consumer_id in dispenser.reports:
        _add_dynamic_budget(consumer_id)


class DispenserSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        dispenser: EnergyDispenser,
        name: str,
        key: str,
        unit: str | None,
        configured_count: int | None = None,
    ) -> None:
        self.dispenser = dispenser
        self._attr_name = name
        self._attr_unique_id = f"energy_dispenser_{key}"
        self._key = key
        self._configured_count = configured_count
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = "power" if unit == "W" else None

    async def async_added_to_hass(self) -> None:
        unsub = self.hass.bus.async_listen(EVENT_RESULT, self._handle_result)
        self.async_on_remove(unsub)

    @callback
    def _handle_result(self, _event) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self):
        if self._key == "consumer_count":
            return self.dispenser.active_request_count()

        if self._key == "available_power":
            result = self.dispenser.last_result
            if result is not None:
                return round(result.available_power)

            raw_available = self.dispenser.raw_available_power()
            if raw_available is None:
                return 0

            return round(raw_available)

        result = self.dispenser.last_result
        if result is None:
            return 0
        return round(result.unallocated_power)


class BudgetSensor(SensorEntity):
    """Read-only allocation budget keyed permanently by consumer_id."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "W"
    _attr_device_class = "power"
    _attr_state_class = "measurement"

    def __init__(self, dispenser: EnergyDispenser, consumer_id: str, name: str) -> None:
        self.dispenser = dispenser
        self.consumer_id = consumer_id
        self._attr_name = f"Budget {name}"
        # The consumer_id is the permanent identity of this budget entity.
        # Keep the actual entity_id independent from the display name as well.
        self._attr_unique_id = f"energy_dispenser_budget_{consumer_id}"
        self._attr_suggested_object_id = f"budget_{consumer_id}"

    async def async_added_to_hass(self) -> None:
        unsub = self.hass.bus.async_listen(EVENT_RESULT, self._handle_result)
        self.async_on_remove(unsub)

    @callback
    def _handle_result(self, _event) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> int | None:
        budget = self.dispenser.budget_for_consumer(self.consumer_id)
        if budget is None:
            return None
        return round(budget)


class ActualPowerSensor(SensorEntity):
    """Best-known actual power for every registered consumer."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "W"
    _attr_device_class = "power"
    _attr_state_class = "measurement"

    def __init__(self, dispenser: EnergyDispenser, consumer_id: str, name: str) -> None:
        self.dispenser = dispenser
        self.consumer_id = consumer_id
        self._attr_name = f"Actual Power {name}"
        self._attr_unique_id = f"energy_dispenser_actual_power_{consumer_id}"
        self._attr_suggested_object_id = f"actual_power_{consumer_id}"

    async def async_added_to_hass(self) -> None:
        unsub = self.hass.bus.async_listen(EVENT_RESULT, self._handle_result)
        self.async_on_remove(unsub)

    @callback
    def _handle_result(self, _event) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> int | None:
        actual = self.dispenser.actual_power_for_consumer(self.consumer_id)
        if actual is None:
            return None
        return round(actual)
