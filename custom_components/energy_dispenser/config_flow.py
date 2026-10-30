from __future__ import annotations

import re
from time import monotonic
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.helpers import selector

from .const import CONF_AVAILABLE_POWER_ENTITY, DOMAIN
from .validation import RequestValidationError, validate_request_contract

CONSUMERS_KEY = "consumers"


def _manual_contract(user_input: dict[str, Any]) -> dict[str, float]:
    """Convert UI percentages and validate a persistent request."""
    contract = {
        "minimum_power": float(user_input["minimum_power"]),
        "preferred_power": float(user_input["preferred_power"]),
        "maximum_power": float(user_input["maximum_power"]),
        "urgency": float(user_input["urgency"]) / 100.0,
        "surplus_value": float(user_input["surplus_value"]) / 100.0,
        "actual_power": 0.0,
        "settling_time": 10.0,
        "minimum_claim_time": 20.0,
        "report_timeout": 15.0,
    }
    validate_request_contract(**contract)
    return contract


def _slug(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9_-]+", "_", value)
    return value.strip("_-")[:50]


def _consumer_label(item: dict[str, Any]) -> str:
    name = str(item.get("name", "")).strip() or str(item.get("consumer_id", "")).strip()
    consumer_id = str(item.get("consumer_id", "")).strip()
    return f"{name} ({consumer_id})"


def _format_consumer_table(
    configured_consumers: list[dict[str, Any]],
    digital_reports: dict[str, Any],
) -> str:
    """Build a markdown table for the options-flow overview."""
    configured_ids = {
        str(item.get("consumer_id", "")).strip()
        for item in configured_consumers
        if str(item.get("consumer_id", "")).strip()
    }

    lines = [
        "| Type | Consumer-ID | Naam | Vermogen | Status |",
        "|---|---|---|---|---|",
    ]

    for item in configured_consumers:
        consumer_id = str(item.get("consumer_id", "")).strip()
        if not consumer_id:
            continue
        name = str(item.get("name", "")).strip() or consumer_id
        minimum = float(item.get("minimum_power", 0))
        preferred = float(item.get("preferred_power", 0))
        maximum = float(item.get("maximum_power", 0))
        enabled = bool(item.get("enabled", True))
        status = "actief" if enabled else "uit"
        lines.append(
            f"| Manueel | `{consumer_id}` | {name} | "
            f"{minimum:g} / {preferred:g} / {maximum:g} W | {status} |"
        )

    now = monotonic()
    for consumer_id, report in sorted(digital_reports.items()):
        consumer_id = str(consumer_id).strip()
        if not consumer_id or consumer_id in configured_ids:
            continue
        if now - report.updated_at > report.report_timeout:
            continue
        state = str(report.state)
        power = (
            f"{report.minimum_power:g} / {report.preferred_power:g} / "
            f"{report.maximum_power:g} W"
        )
        lines.append(
            f"| Digitaal | `{consumer_id}` | `{consumer_id}` | {power} | {state} |"
        )

    if len(lines) == 2:
        lines.append("| — | — | Geen verbruikers | — | — |")

    return "\n".join(lines)


class EnergyDispenserConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            entity_id = user_input[CONF_AVAILABLE_POWER_ENTITY]
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={CONF_AVAILABLE_POWER_ENTITY: entity_id},
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="Energy Dispenser"): str,
                vol.Required(CONF_AVAILABLE_POWER_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["sensor", "input_number"],
                        device_class="power",
                    )
                ),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    def async_get_options_flow(config_entry):
        return EnergyDispenserOptionsFlow(config_entry)


class EnergyDispenserOptionsFlow(config_entries.OptionsFlow):
    """Manage persistent consumers and the selected Available Power source."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry
        self._consumers: list[dict[str, Any]] = [
            {
                key: value
                for key, value in item.items()
                if key != "demand_mode"
            }
            for item in config_entry.options.get(CONSUMERS_KEY, [])
        ]
        self._available_power_entity = str(
            config_entry.options.get(
                CONF_AVAILABLE_POWER_ENTITY,
                config_entry.data.get(CONF_AVAILABLE_POWER_ENTITY, ""),
            )
        )
        self._pending_available_power_entity = self._available_power_entity

    def _digital_reports(self) -> dict[str, Any]:
        dispenser = getattr(self.config_entry, "runtime_data", None)
        if dispenser is None:
            try:
                dispenser = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id, {}).get("dispenser")
            except AttributeError:
                dispenser = None
        if dispenser is None:
            return {}
        return dict(getattr(dispenser, "reports", {}))

    def _overview_placeholders(self) -> dict[str, str]:
        return {
            "available_power_entity": self._available_power_entity or "onbekend",
            "consumer_table": _format_consumer_table(self._consumers, self._digital_reports()),
        }

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "available_power",
                "add_consumer",
                "edit_consumer",
                "remove_consumer",
                "done",
            ],
            description_placeholders=self._overview_placeholders(),
        )

    async def async_step_available_power(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            self._available_power_entity = user_input[CONF_AVAILABLE_POWER_ENTITY]
            self._pending_available_power_entity = self._available_power_entity
            return await self.async_step_init()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_AVAILABLE_POWER_ENTITY,
                    default=self._available_power_entity,
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["sensor", "input_number"],
                        device_class="power",
                    )
                )
            }
        )
        state = self.hass.states.get(self._available_power_entity) if self._available_power_entity else None
        current = state.state if state is not None else "unavailable"
        unit = state.attributes.get("unit_of_measurement", "W") if state else ""
        friendly_name = state.name if state else self._available_power_entity or "onbekend"

        return self.async_show_form(
            step_id="available_power",
            data_schema=schema,
            description_placeholders={
                "available_power_entity": self._available_power_entity or "onbekend",
                "available_power_name": friendly_name,
                "available_power_current": current,
                "available_power_unit": unit,
            },
        )

    async def async_step_add_consumer(
        self, user_input: dict[str, Any] | None = None
    ):
        if user_input is not None:
            consumer_id = _slug(user_input["consumer_id"])

            if not consumer_id:
                return self.async_show_form(
                    step_id="add_consumer",
                    data_schema=self._consumer_schema(),
                    errors={"base": "invalid_consumer_id"},
                )

            if any(
                item["consumer_id"] == consumer_id
                for item in self._consumers
            ):
                return self.async_show_form(
                    step_id="add_consumer",
                    data_schema=self._consumer_schema(user_input),
                    errors={"base": "consumer_exists"},
                )

            try:
                contract = _manual_contract(user_input)
            except RequestValidationError as err:
                return self.async_show_form(
                    step_id="add_consumer",
                    data_schema=self._consumer_schema(user_input),
                    errors={"base": err.code},
                )
            except (TypeError, ValueError):
                return self.async_show_form(
                    step_id="add_consumer",
                    data_schema=self._consumer_schema(user_input),
                    errors={"base": "invalid_number"},
                )

            self._consumers.append(
                {
                    "consumer_id": consumer_id,
                    "name": user_input["name"].strip(),
                    "enabled": user_input["enabled"],
                    "minimum_power": contract["minimum_power"],
                    "preferred_power": contract["preferred_power"],
                    "maximum_power": contract["maximum_power"],
                    "urgency": contract["urgency"],
                    "surplus_value": contract["surplus_value"],
                    "allow_import": user_input["allow_import"],
                    "actual_power_entity": str(user_input.get("actual_power_entity", "")).strip(),
                }
            )

            return await self.async_step_init()

        return self.async_show_form(
            step_id="add_consumer",
            data_schema=self._consumer_schema(),
        )

    async def async_step_edit_consumer(
        self, user_input: dict[str, Any] | None = None
    ):
        if not self._consumers:
            return await self.async_step_init()

        if user_input is None:
            options = {
                item["consumer_id"]: _consumer_label(item)
                for item in self._consumers
            }
            schema = vol.Schema(
                {
                    vol.Required("consumer_id"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {"value": key, "label": label}
                                for key, label in options.items()
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            )
            return self.async_show_form(
                step_id="edit_consumer",
                data_schema=schema,
            )

        consumer_id = user_input["consumer_id"]
        consumer = next(
            (item for item in self._consumers if item["consumer_id"] == consumer_id),
            None,
        )
        if consumer is None:
            return await self.async_step_init()

        self._editing_consumer_id = consumer_id
        defaults = dict(consumer)
        defaults["urgency"] = float(defaults.get("urgency", 0.5)) * 100
        defaults["surplus_value"] = float(defaults.get("surplus_value", 1.0)) * 100
        self._edit_defaults = dict(defaults)
        return await self.async_step_edit_consumer_values()

    async def async_step_edit_consumer_values(
        self, user_input: dict[str, Any] | None = None
    ):
        if user_input is not None:
            try:
                contract = _manual_contract(user_input)
            except RequestValidationError as err:
                return self.async_show_form(
                    step_id="edit_consumer_values",
                    data_schema=self._consumer_schema(user_input, include_consumer_id=False),
                    errors={"base": err.code},
                )
            except (TypeError, ValueError):
                return self.async_show_form(
                    step_id="edit_consumer_values",
                    data_schema=self._consumer_schema(user_input, include_consumer_id=False),
                    errors={"base": "invalid_number"},
                )

            consumer_id = self._editing_consumer_id
            for item in self._consumers:
                if item["consumer_id"] == consumer_id:
                    item.update(
                        {
                            "name": user_input["name"].strip(),
                            "enabled": user_input["enabled"],
                            "minimum_power": contract["minimum_power"],
                            "preferred_power": contract["preferred_power"],
                            "maximum_power": contract["maximum_power"],
                            "urgency": contract["urgency"],
                            "surplus_value": contract["surplus_value"],
                            "allow_import": user_input["allow_import"],
                            "actual_power_entity": str(user_input.get("actual_power_entity", "")).strip(),
                        }
                    )
                    break
            return await self.async_step_init()

        return self.async_show_form(
            step_id="edit_consumer_values",
            data_schema=self._consumer_schema(
                getattr(self, "_edit_defaults", None),
                include_consumer_id=False,
            ),
        )

    async def async_step_remove_consumer(
        self, user_input: dict[str, Any] | None = None
    ):
        if not self._consumers:
            return await self.async_step_init()

        if user_input is not None:
            consumer_id = user_input["consumer_id"]
            self._consumers = [
                item
                for item in self._consumers
                if item["consumer_id"] != consumer_id
            ]
            return await self.async_step_init()

        options = {
            item["consumer_id"]: _consumer_label(item)
            for item in self._consumers
        }

        schema = vol.Schema(
            {
                vol.Required("consumer_id"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"value": key, "label": label}
                            for key, label in options.items()
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )

        return self.async_show_form(
            step_id="remove_consumer",
            data_schema=schema,
        )

    async def async_step_done(self, user_input=None):
        return self.async_create_entry(
            title="",
            data={
                CONSUMERS_KEY: self._consumers,
                CONF_AVAILABLE_POWER_ENTITY: self._available_power_entity,
            },
        )

    @staticmethod
    def _consumer_schema(
        defaults: dict[str, Any] | None = None,
        *,
        include_consumer_id: bool = True,
    ) -> vol.Schema:
        defaults = defaults or {}
        fields: dict[Any, Any] = {}
        if include_consumer_id:
            fields[
                vol.Required(
                    "consumer_id",
                    default=defaults.get("consumer_id", ""),
                )
            ] = str
        fields.update(
            {
                vol.Required(
                    "name",
                    default=defaults.get("name", ""),
                ): str,
                vol.Required(
                    "minimum_power",
                    default=defaults.get("minimum_power", 0),
                ): vol.Coerce(float),
                vol.Required(
                    "preferred_power",
                    default=defaults.get("preferred_power", 2000),
                ): vol.Coerce(float),
                vol.Required(
                    "maximum_power",
                    default=defaults.get("maximum_power", 2000),
                ): vol.Coerce(float),
                vol.Required(
                    "urgency",
                    default=defaults.get("urgency", 50),
                ): vol.Coerce(float),
                vol.Required(
                    "surplus_value",
                    default=defaults.get("surplus_value", 100),
                ): vol.Coerce(float),
                vol.Required(
                    "allow_import",
                    default=defaults.get("allow_import", True),
                ): selector.BooleanSelector(),
                vol.Optional(
                    "actual_power_entity",
                    default=defaults.get("actual_power_entity", ""),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(
                        domain=["sensor", "input_number"],
                        device_class="power",
                    )
                ),
                vol.Required(
                    "enabled",
                    default=defaults.get("enabled", True),
                ): selector.BooleanSelector(),
            }
        )
        return vol.Schema(fields)
