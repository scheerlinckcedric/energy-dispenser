from __future__ import annotations

import sys
import types
from pathlib import Path

PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "energy_dispenser"
)

# The core allocator/power-budget modules are intentionally pure Python.
# For unit tests we load those submodules without importing Home Assistant's
# integration __init__.py, so pytest can run without a full HA installation.
pkg = types.ModuleType("energy_dispenser")
pkg.__path__ = [str(PACKAGE_ROOT)]
pkg.__package__ = "energy_dispenser"
sys.modules.setdefault("energy_dispenser", pkg)

# The integration layer imports a small Home Assistant/voluptuous surface at
# module load time. Lightweight stubs keep orchestration tests local and fast;
# they do not pretend to replace full Home Assistant integration tests.
vol = types.ModuleType("voluptuous")
vol.Schema = lambda value: value
vol.Required = lambda key, **_kwargs: key
vol.Optional = lambda key, **_kwargs: key
vol.In = lambda values: values
vol.Coerce = lambda value_type: value_type
sys.modules.setdefault("voluptuous", vol)

homeassistant = types.ModuleType("homeassistant")
homeassistant.__path__ = []
homeassistant_core = types.ModuleType("homeassistant.core")
homeassistant_core.Event = object
homeassistant_core.HomeAssistant = object
homeassistant_core.ServiceCall = object
homeassistant_core.callback = lambda func: func

homeassistant_const = types.ModuleType("homeassistant.const")
homeassistant_const.CONF_NAME = "name"


class ConfigEntry:
    """Small config-entry stand-in for flow lifecycle tests."""


class ConfigFlow:
    """Expose the result helpers used by the integration's config flow."""

    def __init_subclass__(cls, *, domain=None, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.domain = domain

    def async_create_entry(self, *, title, data):
        return {"type": "create_entry", "title": title, "data": data}

    def async_show_form(self, *, step_id, data_schema, **kwargs):
        return {
            "type": "form",
            "step_id": step_id,
            "data_schema": data_schema,
            **kwargs,
        }


class OptionsFlow(ConfigFlow):
    """Model the read-only, post-construction entry property in HA 2026.1."""

    hass = None
    handler = None

    @property
    def config_entry(self):
        if self.hass is None or self.handler is None:
            raise ValueError("The config entry is not available during initialisation")
        return self.hass.config_entries.async_get_known_entry(self.handler)

    def async_show_menu(self, *, step_id, menu_options, **kwargs):
        return {
            "type": "menu",
            "step_id": step_id,
            "menu_options": menu_options,
            **kwargs,
        }


homeassistant_config_entries = types.ModuleType("homeassistant.config_entries")
homeassistant_config_entries.ConfigEntry = ConfigEntry
homeassistant_config_entries.ConfigFlow = ConfigFlow
homeassistant_config_entries.OptionsFlow = OptionsFlow

homeassistant_helpers = types.ModuleType("homeassistant.helpers")
homeassistant_helpers.__path__ = []


class _SelectorConfig(dict):
    def __init__(self, **kwargs):
        super().__init__(kwargs)


class _Selector:
    def __init__(self, config=None):
        self.config = config or {}


homeassistant_helpers_selector = types.ModuleType("homeassistant.helpers.selector")
homeassistant_helpers_selector.EntitySelectorConfig = _SelectorConfig
homeassistant_helpers_selector.EntitySelector = _Selector
homeassistant_helpers_selector.BooleanSelector = _Selector
homeassistant_helpers_selector.SelectSelectorConfig = _SelectorConfig
homeassistant_helpers_selector.SelectSelector = _Selector
homeassistant_helpers_selector.SelectSelectorMode = types.SimpleNamespace(
    DROPDOWN="dropdown"
)
homeassistant_helpers.selector = homeassistant_helpers_selector
homeassistant_helpers_event = types.ModuleType("homeassistant.helpers.event")
homeassistant_helpers_event.async_track_state_change_event = lambda *_args, **_kwargs: None
homeassistant_helpers_event.async_track_time_interval = lambda *_args, **_kwargs: None

sys.modules.setdefault("homeassistant", homeassistant)
sys.modules.setdefault("homeassistant.config_entries", homeassistant_config_entries)
sys.modules.setdefault("homeassistant.const", homeassistant_const)
sys.modules.setdefault("homeassistant.core", homeassistant_core)
sys.modules.setdefault("homeassistant.helpers", homeassistant_helpers)
sys.modules.setdefault("homeassistant.helpers.event", homeassistant_helpers_event)
sys.modules.setdefault("homeassistant.helpers.selector", homeassistant_helpers_selector)
