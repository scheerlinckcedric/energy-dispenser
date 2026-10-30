from __future__ import annotations

from time import monotonic

from .const import ALLOCATION_STEP_W
from .models import Claim, DispenserResult, EnergyReport


class EnergyAllocator:
    """Allocate power without knowing anything about the physical devices."""

    def __init__(self) -> None:
        self._claims: dict[str, Claim] = {}

    def allocate(self, available_power: float, reports: list[EnergyReport]) -> DispenserResult:
        now = monotonic()
        active = {r.consumer_id: r for r in reports if r.state == "active"}
        self._remove_invalid_claims(active)

        effective_available = self._protected_available(available_power, active, now)

        if effective_available >= 0:
            allocations = self._allocate_surplus(effective_available, list(active.values()), now)
        else:
            allocations = self._allocate_import(-effective_available, list(active.values()))

        self._update_claims(allocations, active, now, effective_available)
        total = sum(allocations.values())

        return DispenserResult(
            available_power=effective_available,
            allocations=allocations,
            unallocated_power=max(0.0, effective_available - total),
        )


    def _protected_available(
        self,
        available_power: float,
        active: dict[str, EnergyReport],
        now: float,
    ) -> float:
        """Return a source pool that cannot drop below protected claims.

        The measured source can temporarily fall when a controlled device starts
        consuming power. For a short settling/protection window that drop is not
        treated as a loss of the already granted claim, because the device's
        actual-power feedback may still be lagging behind the physical device.

        A protected claim is therefore a reservation, not merely a preference.
        The complete protected claim set is restored to the allocation pool before
        normal eligibility/marginal allocation is calculated. This is important
        when the measured source falls below a consumer's minimum power.
        """
        protected_total = 0.0
        settling_ceilings: list[float] = []
        for consumer_id, claim in self._claims.items():
            if claim.watts <= 0 or consumer_id not in active:
                continue

            report = active[consumer_id]
            protection_until = max(
                claim.settling_until,
                claim.started_at + report.minimum_claim_time,
            )
            if now < protection_until:
                protected_total += min(claim.watts, report.maximum_power)

            if (
                now < claim.settling_until
                and claim.settling_ceiling is not None
            ):
                settling_ceilings.append(claim.settling_ceiling)

        effective = float(available_power)
        if protected_total > 0:
            effective = max(effective, protected_total)

        if settling_ceilings:
            # Sensor updates are not atomic. During settling, a source sensor
            # may still show the pre-load surplus while actual_power already
            # reports the new load, temporarily counting the same watts twice.
            # The earliest active ceiling is the conservative system-wide cap.
            ceiling = max(protected_total, min(settling_ceilings))
            effective = min(effective, ceiling)

        return effective

    def claim_watts(self, consumer_id: str) -> float:
        claim = self._claims.get(consumer_id)
        return claim.watts if claim is not None else 0.0

    def claim_is_settled(self, consumer_id: str, now: float | None = None) -> bool:
        claim = self._claims.get(consumer_id)
        if claim is None:
            return False
        current = monotonic() if now is None else now
        return current >= claim.settling_until

    def _remove_invalid_claims(self, active: dict[str, EnergyReport]) -> None:
        for consumer_id in list(self._claims):
            if consumer_id not in active or self._claims[consumer_id].watts <= 0:
                self._claims.pop(consumer_id, None)

    def _allocate_surplus(
        self, available: float, reports: list[EnergyReport], now: float
    ) -> dict[str, float]:
        allocations = {r.consumer_id: 0.0 for r in reports}
        remaining = available

        # A minimum_power is a hard floor: a consumer must be able to receive
        # its complete minimum before it gets any allocation. This prevents
        # meaningless partial budgets such as 342 W for a 1400 W minimum.
        # Consumers whose minimum cannot currently be reached simply remain at
        # 0 W and their power stays available for other consumers.
        eligible = [
            report
            for report in reports
            if report.maximum_power > 0
            and report.minimum_power <= remaining
        ]

        # Protect an existing claim while it is settling or within its minimum
        # claim time, but never violate the hard minimum rule.
        for report in eligible:
            claim = self._claims.get(report.consumer_id)
            if claim is None or claim.watts <= 0:
                continue

            protection_until = max(
                claim.settling_until,
                claim.started_at + report.minimum_claim_time,
            )
            protected = now < protection_until
            if not protected:
                continue

            grant = min(claim.watts, report.maximum_power, remaining)
            if grant < report.minimum_power:
                continue

            allocations[report.consumer_id] = grant
            remaining -= grant

        # Fill in small slices. Equal marginal value is explicitly fair-shared
        # by preferring the consumer with the lowest current allocation. This
        # prevents max() tie-breaking from starving consumers earlier in the
        # list.
        while remaining > 0:
            candidate = self._best_candidate(reports, allocations, remaining)
            if candidate is None:
                break

            _, report = candidate
            headroom = max(0.0, report.maximum_power - allocations[report.consumer_id])
            minimum_deficit = max(0.0, report.minimum_power - allocations[report.consumer_id])
            if minimum_deficit > 0:
                # Starting a consumer is atomic up to its minimum. An
                # allow_import consumer may exceed the remaining surplus here;
                # the excess is explicitly a grid import. For non-import
                # consumers the hard minimum must fit inside the surplus pool.
                if report.allow_import and minimum_deficit > remaining:
                    grant = min(minimum_deficit, headroom)
                else:
                    grant = min(minimum_deficit, remaining, headroom)
            else:
                grant = min(ALLOCATION_STEP_W, remaining, headroom)
            if grant <= 0:
                break
            allocations[report.consumer_id] += grant
            remaining -= grant

        return allocations

    def _best_candidate(
        self,
        reports: list[EnergyReport],
        allocations: dict[str, float],
        remaining: float | None = None,
    ):
        candidates = []
        for report in reports:
            current = allocations[report.consumer_id]
            if current >= report.maximum_power:
                continue

            # A consumer at zero normally may only enter the allocation if its
            # complete minimum can be supplied from the remaining surplus. An
            # import-enabled consumer is the deliberate exception: if it has
            # declared allow_import=true, it may reserve its complete minimum
            # even when the measured surplus is smaller than that minimum. The
            # resulting deficit is imported from the grid and leaves no surplus
            # for consumers behind it.
            if current < report.minimum_power:
                if remaining is not None and report.minimum_power > remaining:
                    if not report.allow_import:
                        continue
                    # Import-enabled start: the consumer accepts that the
                    # missing part of its minimum comes from the grid.
                    score = 4.0 + report.urgency
                else:
                    # This candidate receives its minimum from surplus first.
                    score = 3.0 + report.urgency
            else:
                score = self._marginal_score(report, current)

            if score > 0:
                # Lower current allocation wins exact score ties. This gives
                # equal-value consumers a true fair-share behaviour.
                candidates.append((score, -current, report.consumer_id, report))

        if not candidates:
            return None

        score, _negative_current, _consumer_id, report = max(
            candidates, key=lambda x: (x[0], x[1], x[2])
        )
        return score, report

    @staticmethod
    def _marginal_score(report: EnergyReport, current: float) -> float:
        if current < report.minimum_power:
            return 3.0 + report.urgency

        if current < report.preferred_power:
            progress = (current - report.minimum_power) / max(
                report.preferred_power - report.minimum_power, 1.0
            )
            return 2.0 + report.urgency * (1.0 - progress)

        if current < report.maximum_power:
            progress = (current - report.preferred_power) / max(
                report.maximum_power - report.preferred_power, 1.0
            )
            return report.surplus_value * (1.0 - progress)

        return 0.0

    def _allocate_import(
        self, import_power: float, reports: list[EnergyReport]
    ) -> dict[str, float]:
        allocations = {r.consumer_id: 0.0 for r in reports}
        remaining = import_power

        # Import follows the same hard-minimum rule as surplus allocation.
        # A consumer may only start receiving imported power when its complete
        # minimum can be supplied.
        while remaining > 0:
            candidates = []
            for report in reports:
                if not report.allow_import:
                    continue

                current = allocations[report.consumer_id]
                if current >= report.maximum_power:
                    continue

                if current < report.minimum_power:
                    if report.minimum_power > remaining:
                        continue
                    score = 4.0 + report.urgency
                elif current < report.preferred_power:
                    score = 2.0 + report.urgency
                else:
                    continue

                candidates.append((score, -current, report.consumer_id, report))

            if not candidates:
                break

            _, _negative_current, _consumer_id, report = max(
                candidates, key=lambda x: (x[0], x[1], x[2])
            )

            headroom = max(0.0, report.maximum_power - allocations[report.consumer_id])
            minimum_deficit = max(0.0, report.minimum_power - allocations[report.consumer_id])
            if minimum_deficit > 0:
                grant = min(minimum_deficit, remaining, headroom)
            else:
                grant = min(ALLOCATION_STEP_W, remaining, headroom)

            if grant <= 0:
                break

            allocations[report.consumer_id] += grant
            remaining -= grant

        return allocations

    def _update_claims(
        self,
        allocations,
        reports,
        now: float,
        available_power: float,
    ) -> None:
        for consumer_id, watts in allocations.items():
            report = reports[consumer_id]
            old = self._claims.get(consumer_id)

            if watts <= 0:
                if old is not None:
                    protection_until = max(
                        old.settling_until,
                        old.started_at + report.minimum_claim_time,
                    )
                    if now < protection_until:
                        allocations[consumer_id] = min(old.watts, report.maximum_power)
                        continue
                self._claims.pop(consumer_id, None)
                continue

            if old is None:
                self._claims[consumer_id] = Claim(
                    consumer_id=consumer_id,
                    watts=watts,
                    started_at=now,
                    settling_until=now + report.settling_time,
                    settling_ceiling=max(0.0, float(available_power)),
                )
            else:
                old.watts = watts
