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

homeassistant_helpers = types.ModuleType("homeassistant.helpers")
homeassistant_helpers.__path__ = []
homeassistant_helpers_event = types.ModuleType("homeassistant.helpers.event")
homeassistant_helpers_event.async_track_state_change_event = lambda *_args, **_kwargs: None
homeassistant_helpers_event.async_track_time_interval = lambda *_args, **_kwargs: None

sys.modules.setdefault("homeassistant", homeassistant)
sys.modules.setdefault("homeassistant.core", homeassistant_core)
sys.modules.setdefault("homeassistant.helpers", homeassistant_helpers)
sys.modules.setdefault("homeassistant.helpers.event", homeassistant_helpers_event)
