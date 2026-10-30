# Persistent consumers

A persistent consumer is configured in the Energy Dispenser UI. It remains a
request until you disable or delete it, so no reporting automation is needed.
You may optionally select an actual-power entity in the form.

## Fixed load

Use equal minimum, preferred, and maximum values for an all-or-nothing device:

```text
minimum_power:   2000 W
preferred_power: 2000 W
maximum_power:   2000 W
allow_import:    false
```

The result is either `0 W` or `2000 W`. A separate automation still has to read
the budget sensor and safely control the device.

## Flexible load

Use a range for a device that can genuinely modulate its consumption:

```text
minimum_power:    500 W
preferred_power: 1500 W
maximum_power:   2000 W
allow_import:    false
```

Once the minimum can be met, the granted budget may be any value up to the
maximum. Do not configure a range for a binary device unless its processor can
meaningfully translate every possible granted value.

