from __future__ import annotations

from typing import Protocol

from .models import EnergyReport


class EnergyConsumer(Protocol):
    """Interface for an independent consumer extension."""

    consumer_id: str

    def build_report(self) -> EnergyReport:
        ...

    async def async_apply_allocation(self, watts: float) -> None:
        ...
