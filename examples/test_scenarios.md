# Test scenarios

These are intentionally small scenarios for a public/demo installation.

## 1. Single boiler

```text
Available Power: 2500 W
Boiler: min 500 / preferred 2000 / max 2000

Expected budget: 2000 W
Unallocated: 500 W
```

## 2. Hard maximum

```text
Available Power: 7064 W
Consumer: min 10 / preferred 40 / max 85

Expected budget: 85 W
```

## 3. Equal sharing

```text
Available Power: 6500 W
Consumer A: 1500 / 3000 / 5000
Consumer B: 1500 / 3000 / 5000

Expected: 3250 W + 3250 W
```

## 4. EV starts drawing power

```text
Cycle 1:
  measured source = 3300 W
  actual controlled power = 0 W
  available = 3300 W

Cycle 2:
  EV physically starts using 2000 W
  measured source = 1300 W
  EV feedback is delayed = 0 W
  protected claim = 3300 W
  available = 3300 W

Cycle 3:
  measured source = 1300 W
  reported EV actual power = 2000 W
  available = 3300 W
```

The allocator should not punish the EV just because P1/net surplus now sees the EV load.

## 5. Solar changes

```text
Current:
  measured source = 1300 W
  reported actual power = 2000 W
  available = 3300 W

Then PV drops:
  measured source = 700 W
  reported actual power = 2000 W
  available = 2700 W
```

After claim protection expires, the source change is preserved. Allocations are
never treated as measured power.

## 6. Overlapping sensor updates

```text
Claim started with available = 4000 W
Source sensor temporarily still reports = 4000 W
EV actual-power sensor now reports = 4000 W
Naive candidate = 8000 W
Settling ceiling = 4000 W
Expected effective available = 4000 W
```

The ceiling applies only during `settling_time`.

## 7. Consumer stops

If the consumer becomes inactive, its old allocation is excluded from the next reservation snapshot.
