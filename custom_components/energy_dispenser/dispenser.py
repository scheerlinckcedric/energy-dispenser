from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from time import monotonic
from typing import Any, Callable

import voluptuous as vol
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval

from .allocator import EnergyAllocator
from .const import (
    DEFAULT_CYCLE_INTERVAL,
    DEFAULT_REPORT_TIMEOUT,
    EVENT_ALLOCATION,
    EVENT_REPORT,
    EVENT_REQUEST,
    EVENT_RESULT,
    SERVICE_REPORT,
)
from .models import DispenserResult, EnergyReport
from .power_units import power_to_watts
from .validation import RequestValidationError

_LOGGER = logging.getLogger(__name__)


class EnergyDispenser:
    """Central cycle-based energy allocator."""

    def __init__(self, hass: HomeAssistant, available_entity: str) -> None:
        self.hass = hass
        self.available_entity = available_entity
        self.allocator = EnergyAllocator()
        self.reports: dict[str, EnergyReport] = {}
        self.last_result = None
        self.configured_consumer_count = 0
        self.configured_consumer_ids: set[str] = set()
        self.configured_consumers: dict[str, dict[str, Any]] = {}
        self._unsub_state = None
        self._unsub_report = None
        self._unsub_request = None
        self._unsub_interval = None
        self._distribution_task: asyncio.Task | None = None
        self._distribution_requested = False
        self._budget_entity_adder: Callable[[str], None] | None = None

    async def async_start(self) -> None:
        self._unsub_report = self.hass.bus.async_listen(EVENT_REPORT, self._handle_report)
        # Backward compatibility with the prototype.
        self._unsub_request = self.hass.bus.async_listen(EVENT_REQUEST, self._handle_report)
        self.hass.services.async_register(
            DOMAIN,
            SERVICE_REPORT,
            self._async_handle_report_service,
            schema=REPORT_SERVICE_SCHEMA,
        )

        @callback
        def _run_cycle(_now) -> None:
            self._request_distribution()

        self._unsub_interval = async_track_time_interval(
            self.hass,
            _run_cycle,
            timedelta(seconds=DEFAULT_CYCLE_INTERVAL),
        )
        self._unsub_state = async_track_state_change_event(
            self.hass,
            [self.available_entity],
            self._state_changed,
        )

    async def async_stop(self) -> None:
        for unsubscribe in (
            self._unsub_state,
            self._unsub_report,
            self._unsub_request,
            self._unsub_interval,
        ):
            if unsubscribe:
                unsubscribe()

        if self.hass.services.has_service(DOMAIN, SERVICE_REPORT):
            self.hass.services.async_remove(DOMAIN, SERVICE_REPORT)

        task = self._distribution_task
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._distribution_task = None
        self._distribution_requested = False

    @callback
    def set_configured_consumers(self, consumers: list[dict[str, Any]]) -> None:
        """Store persistent form-configured consumer requests."""
        self.configured_consumers = {
            str(item.get("consumer_id", "")).strip(): dict(item)
            for item in consumers
            if str(item.get("consumer_id", "")).strip()
            and bool(item.get("enabled", True))
        }

    @callback
    def set_budget_entity_adder(self, callback_fn: Callable[[str], None]) -> None:
        """Register the sensor platform callback for dynamically reported consumers."""
        self._budget_entity_adder = callback_fn

    @callback
    def _handle_report(self, event: Event) -> None:
        self._accept_report(event.data)

    async def _async_handle_report_service(self, call: ServiceCall) -> None:
        self._accept_report(call.data)

    @callback
    def _accept_report(self, data: dict[str, Any]) -> None:
        consumer_id = str(data.get("consumer_id", "")).strip()
        if not consumer_id:
            return

        state = str(data.get("state", "active")).lower().strip()
        if state not in {"active", "inactive"}:
            return

        try:
            report = EnergyReport(
                consumer_id=consumer_id,
                state=state,
                minimum_power=data.get("minimum_power", 0),
                preferred_power=data.get("preferred_power", 0),
                maximum_power=data.get("maximum_power", 0),
                urgency=data.get("urgency", 0),
                surplus_value=data.get("surplus_value", 0),
                actual_power=data.get("actual_power", 0),
                settling_time=data.get("settling_time", 10),
                minimum_claim_time=data.get("minimum_claim_time", 20),
                report_timeout=data.get("report_timeout", DEFAULT_REPORT_TIMEOUT),
                allow_import=bool(data.get("allow_import", True)),
            )
        except RequestValidationError as err:
            _LOGGER.warning("Rejected report for %s: %s", consumer_id, err)
            return
        except (TypeError, ValueError) as err:
            _LOGGER.warning("Rejected report for %s: invalid numeric value (%s)", consumer_id, err)
            return

        self.reports[consumer_id] = report

        if self._budget_entity_adder is not None:
            self._budget_entity_adder(consumer_id)

        self._request_distribution()

    @callback
    def _state_changed(self, _event: Event) -> None:
        self._request_distribution()

    @callback
    def _request_distribution(self) -> None:
        """Coalesce triggers into one serial allocation worker instead of a task backlog."""
        self._distribution_requested = True
        if self._distribution_task is None or self._distribution_task.done():
            self._distribution_task = self.hass.async_create_task(
                self._distribution_worker()
            )

    async def _distribution_worker(self) -> None:
        while self._distribution_requested:
            self._distribution_requested = False
            await self.async_distribute()

    def _read_actual_power_entity(self, consumer: dict[str, Any]) -> float | None:
        entity_id = str(consumer.get("actual_power_entity", "")).strip()
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        try:
            unit = state.attributes.get("unit_of_measurement")
            return max(0.0, power_to_watts(state.state, unit))
        except (TypeError, ValueError):
            return None

    def raw_available_power(self) -> float | None:
        """Read and normalize the configured Available Power source to watts."""
        state = self.hass.states.get(self.available_entity)
        if state is None:
            return None
        try:
            unit = state.attributes.get("unit_of_measurement")
            return power_to_watts(state.state, unit)
        except (TypeError, ValueError):
            return None

    def actual_power_for_consumer(self, consumer_id: str) -> float | None:
        """Return the best-known actual power for a registered consumer."""
        report = self.reports.get(consumer_id)
        if report is not None:
            now = monotonic()
            if now - report.updated_at <= report.report_timeout:
                return max(0.0, report.actual_power)

        configured = self.configured_consumers.get(consumer_id)
        if configured is not None:
            return self._read_actual_power_entity(configured)

        return None

    def request_is_active(self, consumer_id: str, now: float | None = None) -> bool:
        """Return whether a consumer currently has an active request contract."""
        current = monotonic() if now is None else now
        report = self.reports.get(consumer_id)
        if report is not None and current - report.updated_at <= report.report_timeout:
            return report.state == "active"
        return consumer_id in self.configured_consumers

    def budget_for_consumer(self, consumer_id: str) -> float | None:
        """Return the granted budget, or None when no request is active."""
        if not self.request_is_active(consumer_id):
            return None
        if self.last_result is None:
            return 0.0
        return self.last_result.allocations.get(consumer_id, 0.0)

    def active_request_count(self, now: float | None = None) -> int:
        """Count manual and automated requests that are currently active."""
        current = monotonic() if now is None else now
        return len(self._build_active_reports(current))

    def _build_active_reports(self, now: float) -> list[EnergyReport]:
        """Build the immutable cycle snapshot, keeping configured requests persistent."""
        active: list[EnergyReport] = []

        for consumer_id, configured in self.configured_consumers.items():
            if not bool(configured.get("enabled", True)):
                continue

            report = self.reports.get(consumer_id)
            if (
                report is not None
                and now - report.updated_at <= report.report_timeout
            ):
                if report.state == "active":
                    active.append(report)
                # A fresh explicit inactive report suppresses the persistent
                # configured request for this cycle.
                continue

            actual_power = self._read_actual_power_entity(configured)
            active.append(
                EnergyReport(
                    consumer_id=consumer_id,
                    state="active",
                    minimum_power=float(configured.get("minimum_power", 0)),
                    preferred_power=float(configured.get("preferred_power", 0)),
                    maximum_power=float(configured.get("maximum_power", 0)),
                    urgency=float(configured.get("urgency", 0.5)),
                    surplus_value=float(configured.get("surplus_value", 1.0)),
                    actual_power=actual_power or 0.0,
                    allow_import=bool(configured.get("allow_import", True)),
                )
            )

        # Digital-only consumers exist only while their report lease is valid.
        for consumer_id, report in self.reports.items():
            if consumer_id in self.configured_consumers:
                continue
            if report.state == "active" and now - report.updated_at <= report.report_timeout:
                active.append(report)

        return active

    async def async_distribute(self) -> None:
        raw_available = self.raw_available_power()
        if raw_available is None:
            self._publish_source_unavailable()
            return

        now = monotonic()
        active = self._build_active_reports(now)

        # The configured source is the measured net surplus. Controlled
        # consumers can already be reducing that measurement, so add back only
        # their currently observed actual power. This reconstructs the power
        # available before ED-controlled loads without counting manual/uncontrolled
        # consumers a second time.
        controlled_actual = 0.0
        for report in active:
            if self.allocator.claim_watts(report.consumer_id) <= 0:
                continue
            actual = self.actual_power_for_consumer(report.consumer_id)
            if actual is not None:
                controlled_actual += max(0.0, actual)

        available = raw_available + controlled_actual

        self.reports = {
            consumer_id: report
            for consumer_id, report in self.reports.items()
            if now - report.updated_at <= report.report_timeout
        }

        # One immutable snapshot is used for this complete allocation cycle.
        result = self.allocator.allocate(available, active)
        self._publish_result(
            result,
            raw_available,
            source_available=True,
            consumer_count=len(active),
        )

    def _publish_source_unavailable(self) -> None:
        """Fail closed when the configured power source cannot be read."""
        known_consumer_ids = (
            set(self.configured_consumer_ids)
            | set(self.configured_consumers)
            | set(self.reports)
        )
        if self.last_result is not None:
            known_consumer_ids.update(self.last_result.allocations)

        # An empty report snapshot clears protected allocator claims as well as
        # the public budgets. A recovered source therefore starts a fresh cycle.
        self.allocator.allocate(0, [])
        result = DispenserResult(
            available_power=0,
            allocations={consumer_id: 0.0 for consumer_id in known_consumer_ids},
            unallocated_power=0,
        )
        self._publish_result(
            result,
            0,
            source_available=False,
            consumer_count=self.active_request_count(),
        )

    def _publish_result(
        self,
        result: DispenserResult,
        raw_available: float,
        *,
        source_available: bool,
        consumer_count: int,
    ) -> None:
        """Publish one complete allocation result to events and sensors."""
        self.last_result = result

        for consumer_id, watts in result.allocations.items():
            self.hass.bus.async_fire(
                EVENT_ALLOCATION,
                {
                    "consumer_id": consumer_id,
                    "allocated_power": round(watts, 1),
                    "available_power": round(result.available_power, 1),
                    "raw_available_power": round(raw_available, 1),
                    "source_available": source_available,
                },
            )

        self.hass.bus.async_fire(
            EVENT_RESULT,
            {
                "available_power": round(result.available_power, 1),
                "raw_available_power": round(raw_available, 1),
                "unallocated_power": round(result.unallocated_power, 1),
                "allocations": {k: round(v, 1) for k, v in result.allocations.items()},
                "consumer_count": consumer_count,
                "source_available": source_available,
            },
        )


# Kept local to avoid coupling the generic report contract to device-specific code.
DOMAIN = "energy_dispenser"
REPORT_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Required("consumer_id"): str,
        vol.Optional("state", default="active"): vol.In({"active", "inactive"}),
        vol.Optional("minimum_power", default=0): vol.Coerce(float),
        vol.Optional("preferred_power", default=0): vol.Coerce(float),
        vol.Optional("maximum_power", default=0): vol.Coerce(float),
        vol.Optional("urgency", default=0): vol.Coerce(float),
        vol.Optional("surplus_value", default=0): vol.Coerce(float),
        vol.Optional("actual_power", default=0): vol.Coerce(float),
        vol.Optional("settling_time", default=10): vol.Coerce(float),
        vol.Optional("minimum_claim_time", default=20): vol.Coerce(float),
        vol.Optional("report_timeout", default=DEFAULT_REPORT_TIMEOUT): vol.Coerce(float),
        vol.Optional("allow_import", default=True): bool,
    }
)
