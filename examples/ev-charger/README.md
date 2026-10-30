# EV charger example

This advanced example shows a flexible consumer. The requester reports a range
in watts. The processor converts the granted watt budget to charger current.

- [`requester.yaml`](requester.yaml) reports the charge request every 2 seconds.
- [`processor.yaml`](processor.yaml) samples non-zero budgets every 15 seconds,
  changes current only by whole amps, and stops immediately at a zero budget.

The example assumes a single-phase charger with a `6 A` minimum and a `20 A`
maximum. At approximately `230 V`, that is a range of about `1380–4600 W`.
Replace these limits and all entity IDs with the verified capabilities of your
charger and electrical installation.

`settling_time` and `minimum_claim_time` protect the allocation model; they do
not rate-limit commands to the charger. The 15-second sampling and 1 A steps in
the processor serve that separate product-specific purpose.

This is an illustrative automation, not certified EVSE control. Keep the
charger's own current, thermal, cable, phase, and installation protections in
place.
