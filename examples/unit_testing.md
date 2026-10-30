# Unit testing

The allocator is deliberately kept independent from Home Assistant so the core rules can be tested without any hardware.

From the integration directory:

```bash
python -m pytest -q
```

Or install pytest first:

```bash
python -m pip install pytest
python -m pytest -q
```

The public tests cover:

- hard minimums
- hard maximums
- fair sharing between equal consumers
- allowed versus disallowed grid import
- the Available Power feedback correction
- multiple active allocations
- negative source power
- inactive consumers and public examples

### Feedback regression test

This is the important real-world case:

```text
Before EV starts:
  raw source                3300 W
  EV actual power              0 W
  effective available       3300 W

EV starts, actual-power feedback is still delayed:
  raw source                1300 W
  EV actual power              0 W
  protected claim           3300 W
  effective available       3300 W

Feedback has settled:
  raw source                1300 W
  EV actual power           2000 W
  candidate available       3300 W
  effective available       3300 W
```

The EV's own load therefore does not make the Energy Dispenser destroy the budget it just allocated.

The source can still change independently. Claim protection may deliberately
delay a reduction until `settling_time`/`minimum_claim_time` expires.


### Available Power source tests

Raw Available Power is exactly the configured source entity. The distributable
candidate adds measured actual power only for consumers with a current claim.
Allocations themselves are never added.

Example:

```text
raw source              900 W
EV actual power        1220 W
candidate available    2120 W
```

During `settling_time`, a protected floor prevents collapse and a temporary
ceiling prevents a stale source plus fresh actual-power value from counting the
same watts twice. The ceiling ends with settling; `minimum_claim_time` can keep
only the floor active for longer.

See `../docs/power-model.md` for the complete formula and timelines.

### Digital reporting tests

Digital requesters report regularly. The built-in requester interval is 2 seconds,
while `report_timeout` controls when a digital-only consumer is considered stale.
These are separate concepts from a device's `settling_time`.
