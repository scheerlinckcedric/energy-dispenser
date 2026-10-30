# Test consumer

This is the safest place to start. The automation reports a flexible request,
but there is deliberately no processor and therefore no physical device is
controlled.

Copy [`requester.yaml`](requester.yaml) into your Home Assistant automations,
reload automations, and inspect `sensor.budget_example_test_consumer`. Change
the Available Power source and observe how the granted budget changes between
`0 W` and `1000 W`.

Because this simulated consumer never actually uses its budget, it reports
`actual_power: 0`. Do not use that pattern for a real controlled load: report a
real power measurement whenever one is available.

