# Electric boiler example

This example models a `2000 W` heating element as a fixed, all-or-nothing load.
The requester describes when heat is wanted; the processor decides whether to
operate the example relay.

## Step 1: a simple on/off request

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

- [`requester.yaml`](requester.yaml) reports demand from a simple
  `input_boolean` and measured actual power.
- [`processor.yaml`](processor.yaml) consumes the granted budget.

Start with these two files. They make the requester/processor boundary easy to
see before temperature-dependent behaviour is introduced.

## Step 2: make the requester temperature-aware

Now extend the setup with `sensor.example_boiler_temperature`. We would like
roughly `60 °C`: comfortably warm water for a bath, without treating every
temperature as equally urgent. This example expects that sensor to report
degrees Celsius.

[`temperature-requester.yaml`](temperature-requester.yaml) divides the demand
into four temperature zones:

| Water temperature | Request | Urgency | Grid import |
|---|---|---:|---|
| `65 °C` or warmer | inactive | `0.0` | no |
| `50–65 °C` | fixed `2000 W` | `0.2` | no |
| `38–50 °C` | fixed `2000 W` | `0.6` | no |
| below `38 °C` | fixed `2000 W` | `1.0` | yes |

Above `50 °C`, heating is useful but can patiently wait for surplus. Below
`38 °C`, avoiding cold water becomes important enough that this example allows
the missing power to be imported from the grid. The allocator still receives
the same generic fixed-power contract; only the product-specific requester
decides how temperature affects `state`, `urgency`, and `allow_import`.

Use either [`requester.yaml`](requester.yaml) or
[`temperature-requester.yaml`](temperature-requester.yaml), never both for the
same `example_boiler` consumer ID.

If the temperature sensor is unavailable or non-numeric, the advanced requester
fails safe by reporting an inactive request. It must not turn on a heating
element based on an invented temperature.

## Safety boundary

Replace all example entity IDs. Real boiler control must retain manufacturer
safeguards and normally also needs temperature hysteresis, over-temperature
protection, a suitable contactor, and sensible minimum on/off times. Energy
Dispenser does not replace any of those protections. The `65 °C` software
threshold is comfort logic, not a certified over-temperature cut-out.
