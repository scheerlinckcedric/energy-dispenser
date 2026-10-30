# Electric boiler example

This example models a `2000 W` heating element as a fixed, all-or-nothing load.
The requester describes when heat is wanted; the processor decides whether to
operate the example relay.

```text
input_boolean.example_boiler_needs_heat
                  |
                  v
        requester.yaml
                  |
       2000 W fixed request
                  v
         Energy Dispenser
                  |
 sensor.budget_example_boiler
                  v
         processor.yaml
                  |
                  v
 switch.example_boiler_relay
```

The request uses `minimum = preferred = maximum = 2000 W`. That matches the
binary processor: the boiler receives either its complete rated power or zero.
With `allow_import: false`, insufficient surplus does not start it.

- [`requester.yaml`](requester.yaml) reports demand and measured actual power.
- [`processor.yaml`](processor.yaml) consumes the granted budget.

Replace all example entity IDs. Real boiler control must retain manufacturer
safeguards and normally also needs temperature hysteresis, over-temperature
protection, a suitable contactor, and sensible minimum on/off times. Energy
Dispenser does not replace any of those protections.
