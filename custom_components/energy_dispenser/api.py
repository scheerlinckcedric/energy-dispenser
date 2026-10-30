from __future__ import annotations

from typing import Any, Callable, Awaitable

from homeassistant.core import Event, HomeAssistant

from .const import EVENT_ALLOCATION, EVENT_REPORT, EVENT_REQUEST
from .models import EnergyReport


class EnergyDispenserAPI:
    """Public API exposed to type-less energy requesters."""

    def __init__(self, dispenser) -> None:
        self.dispenser = dispenser
        self.hass: HomeAssistant = dispenser.hass

    async def async_submit_report(self, report: EnergyReport) -> None:
        await async_submit_report(self.hass, report)

    async def async_submit_request(self, report: EnergyReport) -> None:
        await async_submit_request(self.hass, report)

    def listen_allocation(
        self,
        consumer_id: str,
        callback: Callable[[float], Any],
    ):
        return listen_allocation(self.hass, consumer_id, callback)


def get_dispenser(hass: HomeAssistant):
    from .const import DOMAIN
    data = hass.data.get(DOMAIN, {})
    if not data:
        return None
    first = next(iter(data.values()), None)
    return first.get("dispenser") if first else None


async def async_submit_report(hass: HomeAssistant, report: EnergyReport) -> None:
    hass.bus.async_fire(EVENT_REPORT, _report_to_event_data(report))


async def async_submit_request(hass: HomeAssistant, report: EnergyReport) -> None:
    hass.bus.async_fire(EVENT_REQUEST, _report_to_event_data(report))


def listen_allocation(hass: HomeAssistant, consumer_id: str, callback):
    async def _handle(event: Event):
        if str(event.data.get("consumer_id", "")) != consumer_id:
            return
        result = callback(float(event.data.get("allocated_power", 0)))
        if result is not None:
            await result

    return hass.bus.async_listen(EVENT_ALLOCATION, _handle)


def _report_to_event_data(report: EnergyReport) -> dict[str, Any]:
    return {
        "consumer_id": report.consumer_id,
        "state": report.state,
        "minimum_power": report.minimum_power,
        "preferred_power": report.preferred_power,
        "maximum_power": report.maximum_power,
        "urgency": report.urgency,
        "surplus_value": report.surplus_value,
        "actual_power": report.actual_power,
        "settling_time": report.settling_time,
        "minimum_claim_time": report.minimum_claim_time,
        "report_timeout": report.report_timeout,
        "allow_import": report.allow_import,
    }
