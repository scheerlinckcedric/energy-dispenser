# Available Power, feedback, and timing

This document is the authoritative description of the Energy Dispenser power
model. It explains how source measurements, device feedback, claims, and the
three timing settings interact.

![Available Power reconstruction and temporary claim protection](diagrams/available-power.svg)

## Why feedback correction is necessary

The configured Available Power entity normally measures net surplus after all
loads in the home. When an Energy Dispenser-controlled device starts consuming,
that same source measurement falls. If the allocator used the falling value
directly, a device would destroy the budget that just started it.

Energy Dispenser therefore distinguishes these values:

- `raw_available_power`: the current configured source measurement;
- `controlled_actual_power`: measured consumption from consumers that currently
  have an Energy Dispenser claim;
- `candidate_available_power`: the reconstructed pool before those controlled
  loads;
- `effective_available_power`: the pool after temporary claim protection.

The normal reconstruction is:

```text
candidate_available_power
    = raw_available_power
    + sum(controlled_actual_power)
```

Budgets, preferred power, and maximum power are never added to this formula.
Only measured actual power from currently controlled consumers is added back.
Uncontrolled household loads remain part of the raw source measurement.

All exchanged power values are absolute watts, not deltas.

### Unit boundary

Configured Home Assistant source and actual-power entities are converted from
`mW`, `W`, `kW`, or `MW` to watts at the integration boundary. Unitless entities
are interpreted as watts for input-number compatibility. An unsupported or
non-finite source value fails closed; an unsupported optional actual-power value
is treated as unknown.

The `energy_dispenser.report` API is already inside that boundary. Requesters
must therefore send `minimum_power`, `preferred_power`, `maximum_power`, and
`actual_power` in watts. For example, a requester reading `1.216 kW` reports
`1216 W`.

## Why reconstruction alone is not enough

Home Assistant sensors are not updated atomically. A fast P1/grid sensor may
show the load immediately while an EV charger reports its consumption several
seconds later. The opposite overlap can also occur: charger feedback may update
while the source still contains the old surplus.

Without protection, those delays can cause either:

- a false drop to `0 W`, stopping the device that just started; or
- a false increase, counting the same watts twice and raising a `4000 W` budget
  toward an EV's `7800 W` maximum.

Energy Dispenser protects a new claim with a temporary floor and ceiling.

## Protected floor

While a claim is protected, its existing allocation is a reservation. The
effective pool cannot fall below the sum of protected claims:

```text
protected_floor = sum(protected claim watts)
effective_available_power >= protected_floor
```

The floor remains active until the later of:

- `settling_time`; and
- `minimum_claim_time`.

This prevents delayed feedback or a short source dip from immediately removing
an existing allocation.

## Settling ceiling

When a claim starts, Energy Dispenser stores the effective power pool seen in
that allocation cycle. During `settling_time`, that stored value is a temporary
system-wide ceiling:

```text
effective_available_power <= settling ceiling
```

If multiple claims are settling, the earliest active ceiling is used. The
ceiling is never allowed below the protected floor; explicit grid-import claims
can therefore still receive their complete hard minimum.

The ceiling ends after `settling_time`. `minimum_claim_time` does **not** extend
it. Consequently, genuine new solar surplus may be used once measurements are
expected to have settled, even if an existing claim is still protected from
being stopped.

The complete protection rule is conceptually:

```text
candidate = raw source + controlled actual power
effective = max(candidate, protected floor)

while a claim is settling:
    effective = min(effective, max(protected floor, settling ceiling))
```

## The timing settings are different

| Setting | Purpose | What it does not mean |
|---|---|---|
| `settling_time` | Time allowed for device control and sensors to reflect a newly started claim. Enables both the floor and temporary ceiling. | It is not a physical minimum run time. |
| `minimum_claim_time` | Minimum time the allocator protects an existing claim from disappearing. Extends the floor only. | It does not keep the settling ceiling active. |
| report interval | How often a requester sends state and `actual_power`. The built-in requester uses 2 seconds. | It is not a protection duration. |
| `report_timeout` | Lease lifetime for an automated report. A digital-only requester becomes inactive after this silence. | It does not describe device reaction speed. |

In the current model, these timers start when a consumer receives its first
non-zero claim. Updating an existing claim does not restart them. When a claim
ends and later starts again, new timers and a new settling ceiling are created.

## EV example: delayed charger feedback

An EV requests:

```text
minimum:   1500 W
preferred: 2400 W
maximum:   7800 W
settling_time:      20 s
minimum_claim_time: 60 s
```

The home initially exports `4000 W`:

| Time | Raw source | EV actual | Candidate | Protected range | Effective pool | EV budget |
|---|---:|---:|---:|---:|---:|---:|
| 0 s | 4000 W | 0 W | 4000 W | new claim | 4000 W | 4000 W |
| 3 s | 500 W | 0 W | 500 W | 4000–4000 W | 4000 W | 4000 W |
| 8 s | 0 W | 4000 W | 4000 W | 4000–4000 W | 4000 W | 4000 W |
| 15 s | 4000 W stale | 4000 W | 8000 W | 4000–4000 W | 4000 W | 4000 W |
| 21 s | 0 W | 4000 W | 4000 W | floor only | 4000 W | 4000 W |

The `8000 W` overlap at 15 seconds is capped. After 20 seconds the ceiling is
gone, but the 4000 W floor remains until 60 seconds because of
`minimum_claim_time`.

## Example: real source change

Suppose solar production genuinely rises from `4000 W` to `6000 W` five seconds
after the EV starts. The settling ceiling deliberately delays use of that extra
`2000 W` until `settling_time` ends. This is the stability trade-off: a small
amount of surplus may remain unused briefly instead of causing rapid budget
changes based on unsynchronised measurements.

If production falls, the protected floor can temporarily cause grid import.
That behavior lasts only for the configured protection period and is the reason
timings should be no longer than necessary.

## Example: different timer values

```text
settling_time = 10 s
minimum_claim_time = 60 s
```

- seconds 0–10: the claim has a floor and ceiling;
- seconds 10–60: measurements may change or grow the pool, but the existing
  claim retains its floor;
- after 60 seconds: neither protection remains.

With `settling_time = 30 s` and `minimum_claim_time = 10 s`, both floor and
ceiling remain for 30 seconds because settling is the longer protection.

## Device command stability belongs in the processor

Allocator stability does not mean a physical device should follow every small
budget change. Product-specific processors must translate the budget into safe,
stable commands.

Examples:

- an EV processor can change current at most once every 10–30 seconds and only
  when the result differs by at least 1 A;
- an air-conditioner processor can use mode thresholds with hysteresis so it
  does not alternate between fan levels 1 and 3;
- a boiler processor can enforce temperature hysteresis and minimum run time.

Those rules depend on the product and remain outside the generic allocator.
`minimum_claim_time` protects an allocation contract; it does not replace a
device's operational or safety controls.

## Choosing initial values

Start with measured behavior rather than large safety margins:

- set `settling_time` slightly above the worst observed delay between issuing a
  command and both source and actual-power sensors agreeing;
- set `minimum_claim_time` to the shortest allocation hold that prevents
  undesirable start/stop cycling;
- keep reporting comfortably faster than `report_timeout` (for example every
  2 seconds with a 15-second timeout);
- put command rate limits, step sizes, and physical minimum run times in the
  product processor.

For a first EV test, `settling_time: 20` and `minimum_claim_time: 20–60` are
reasonable starting points, but recorded sensor delays should determine the
final values.

## Failure behavior

If the configured Available Power source is missing or non-numeric, active
budgets fail closed to `0 W` and protected claims are cleared. An inactive
requester has no current budget contract, so its budget sensor is unavailable
rather than `0 W`.
