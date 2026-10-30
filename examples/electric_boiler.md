# Public example: electric boiler

A very common Home Assistant use case is an electric boiler that heats water with solar surplus.
The Energy Dispenser only decides **how much power the boiler may use**. A separate processor decides how to switch the real relay, smart plug or contactor.

## Simple architecture

```text
 Solar / grid sensors
        |
        v
 +---------------------+
 | Energy Dispenser    |
 |                     |
 | available power     |
 | boiler request      |
 | EV request          |
 +----------+----------+
            |
            | budget_example_boiler
            v
 +---------------------+
 | Boiler processor    |
 |                     |
 | relay / smart plug  |
 +----------+----------+
            |
            v
      Electric boiler
```

See `diagrams/electric-boiler.svg` for a small visual diagram.

## Example request

The boiler reports:

```text
minimum   1000 W
preferred 2000 W
maximum   2000 W
allow_import = false
```

When the dispenser has 1500 W available, the boiler can receive 1500 W if the allocator rules allow it. When only 700 W is available, the hard minimum prevents a meaningless partial start and the boiler receives 0 W.

## Example requester

See `electric_boiler_requester.yaml`.

The requester is intentionally generic. It does not know how the boiler is switched.

## Example processor

A minimal processor could use the budget like this:

```yaml
- alias: Example - Electric boiler processor
  id: example_electric_boiler_processor
  trigger:
    - platform: state
      entity_id: sensor.budget_example_boiler
    - platform: state
      entity_id: switch.example_boiler_relay

  action:
    - choose:
        - conditions:
            - condition: numeric_state
              entity_id: sensor.budget_example_boiler
              above: 1000
          sequence:
            - action: switch.turn_on
              target:
                entity_id: switch.example_boiler_relay
      default:
        - action: switch.turn_off
          target:
            entity_id: switch.example_boiler_relay
```

That is just an example. A real boiler controller will normally add temperature hysteresis, minimum run time and safety checks.
