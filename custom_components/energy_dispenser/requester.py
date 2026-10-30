from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from datetime import timedelta

from .const import DEFAULT_REPORT_INTERVAL

from .api import EnergyDispenserAPI
from .models import EnergyReport


@dataclass
class DemandRequester:
    """Type-less demand requester."""

    hass: HomeAssistant
    api: EnergyDispenserAPI
    requester_id: str
    minimum_power: float = 0.0
    preferred_power: float = 0.0
    maximum_power: float = 0.0
    urgency: float = 0.0
    surplus_value: float = 0.0
    actual_power: float = 0.0
    allow_import: bool = True
    settling_time: float = 10.0
    minimum_claim_time: float = 20.0
    report_timeout: float = 15.0
    _started: bool = field(default=False, init=False)
    _unsub_report: object | None = field(default=None, init=False)

    async def async_start(self) -> None:
        self._started = True
        await self.async_report()
        @callback
        def _report_tick(_now) -> None:
            self.hass.async_create_task(self._safe_report())

        self._unsub_report = async_track_time_interval(
            self.hass,
            _report_tick,
            timedelta(seconds=DEFAULT_REPORT_INTERVAL),
        )

    async def _safe_report(self) -> None:
        try:
            await self.async_report()
        except Exception:
            self.hass.logger.exception(
                "Energy Dispenser: report failed for consumer %s",
                self.requester_id,
            )

    async def async_stop(self) -> None:
        self._started = False
        if self._unsub_report:
            self._unsub_report()
            self._unsub_report = None

    async def async_report(self) -> None:
        if not self._started:
            return

        await self.api.async_submit_report(
            EnergyReport(
                consumer_id=self.requester_id,
                state="active",
                minimum_power=max(0.0, self.minimum_power),
                preferred_power=max(0.0, self.preferred_power),
                maximum_power=max(0.0, self.maximum_power),
                urgency=min(1.0, max(0.0, self.urgency)),
                surplus_value=min(1.0, max(0.0, self.surplus_value)),
                actual_power=max(0.0, self.actual_power),
                settling_time=self.settling_time,
                minimum_claim_time=self.minimum_claim_time,
                report_timeout=self.report_timeout,
                allow_import=self.allow_import,
            )
        )
