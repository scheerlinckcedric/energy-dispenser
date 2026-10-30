from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import EnergyDispenserAPI
from .const import DOMAIN
from .dispenser import EnergyDispenser
from .requester import DemandRequester

PLATFORMS = ["sensor"]


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration when requester configuration changes."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Energy Dispenser."""
    available_entity = entry.options.get("available_power_entity") or entry.data.get("available_power_entity")
    if not available_entity:
        return False

    dispenser = EnergyDispenser(hass, available_entity)
    api = EnergyDispenserAPI(dispenser)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "dispenser": dispenser,
        "api": api,
        "requesters": {},
    }

    entry.runtime_data = dispenser
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    await dispenser.async_start()

    configured_consumers = entry.options.get("consumers")
    if configured_consumers is None:
        configured_consumers = entry.data.get("consumers", [])

    dispenser.configured_consumer_ids = {
        str(item.get("consumer_id", "")).strip()
        for item in configured_consumers
        if str(item.get("consumer_id", "")).strip()
    }
    dispenser.configured_consumer_count = len(dispenser.configured_consumer_ids)
    dispenser.set_configured_consumers(configured_consumers)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload Energy Dispenser."""
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if data:
        for requester in data.get("requesters", {}).values():
            await requester.async_stop()

        await data["dispenser"].async_stop()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
