# Examples

The examples are organised as a learning path. Start without hardware, continue
with one simple fixed consumer, and then add a flexible consumer. Every example
uses the same separation between demand, allocation, and device control.

## The boundary to remember

```text
requester                  Energy Dispenser                 processor
describes demand    ->     grants a budget in watts   ->   controls the device
```

The requester may read device state and measured power, but it does not apply
the budget. The processor reads `sensor.budget_<consumer_id>` and translates
watts into product-specific commands. Safety, comfort logic, current limits,
relay timing, and protocol details belong in that processor or in the device.

## 1. Test consumer: observe without controlling hardware

The [`test-consumer/`](test-consumer/) example reports a flexible request from
`100 W` to `1000 W`. It has no processor, so nothing physical can be switched.
Use it to observe how `sensor.budget_example_test_consumer` reacts when the
Available Power value changes.

Files:

- [`test-consumer/requester.yaml`](test-consumer/requester.yaml): runnable
  reporting automation;
- [`test-consumer/README.md`](test-consumer/README.md): setup and expected
  behaviour.

## 2. Electric boiler: the simplest physical consumer

The [`electric-boiler/`](electric-boiler/) example models a `2000 W` heating
element as an all-or-nothing load:

```text
minimum = preferred = maximum = 2000 W
```

The requester reports whether heat is needed. Energy Dispenser grants either
`0 W` or the complete `2000 W`. The separate processor translates that budget
into an on/off command for the example relay.

Files:

- [`electric-boiler/requester.yaml`](electric-boiler/requester.yaml): reports
  a simple on/off demand and measured actual power;
- [`electric-boiler/temperature-requester.yaml`](electric-boiler/temperature-requester.yaml):
  makes urgency and import permission depend on water temperature;
- [`electric-boiler/processor.yaml`](electric-boiler/processor.yaml): consumes
  the budget and controls the example relay;
- [`electric-boiler/README.md`](electric-boiler/README.md): contract, flow, and
  safety assumptions.

## 3. EV charger: add a flexible consumer

The [`ev-charger/`](ev-charger/) example shows the next step. An EV charger can
adjust its current and can therefore consume power left over after fixed loads.
Its request uses the measured voltage to express a range from `6 A` to `20 A`,
but the Energy Dispenser contract itself remains entirely in watts.

The processor converts the watt budget back to whole amps. It samples non-zero
budgets every 15 seconds instead of sending a charger command for every small
sensor change, while a zero budget still stops the example charger immediately.

For example, with `4200 W` available, a fixed `2000 W` boiler can run while the
EV receives the remaining `2200 W`. Both devices keep their own product logic;
the allocator only compares their generic requests and grants watt budgets.

Files:

- [`ev-charger/requester.yaml`](ev-charger/requester.yaml): flexible EV demand
  and actual-power reporting;
- [`ev-charger/processor.yaml`](ev-charger/processor.yaml): watt-to-amp
  conversion and command rate limiting;
- [`ev-charger/README.md`](ev-charger/README.md): electrical assumptions and
  the difference between allocator timing and command timing.

## 4. Persistent consumers: configure requests in the UI

Not every consumer needs a reporting automation. The
[`persistent-consumers/`](persistent-consumers/) guide shows fixed and flexible
requests created through the Energy Dispenser configuration UI. They remain
active until disabled or deleted. A processor is still required if the budget
must control a physical device.

## 5. Compact report reference

[`reference/digital-report.yaml`](reference/digital-report.yaml) contains one
compact `energy_dispenser.report` action with every public request field. Use it
as a field reference after working through the complete examples above.

## Adapting an example

Entity IDs in these files are examples. Replace them with the entities from
your own Home Assistant installation. All values sent directly through
`energy_dispenser.report` must be expressed in watts.

The diagrams belong to the technical documentation in [`../docs/diagrams/`](../docs/diagrams/).

