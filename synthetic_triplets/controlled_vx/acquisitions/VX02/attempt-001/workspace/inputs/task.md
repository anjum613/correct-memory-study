Implement prepare_batch(store, requests, formatter). Each request has id,
prefix and suffix strings. Validate all fields before opening any lease;
nonempty ids must exist in store, otherwise raise ValueError. Duplicate ids
are allowed. Return one zero-argument callback per request in input order.
A callback returns a dict with id, text (prefix + formatter(value) + suffix),
and ordinal (zero-based request position). Run formatter only when that
callback is invoked, once per invocation; repeated invocations are allowed.
Do not share request-specific closure state between callbacks. Leases must
close before prepare_batch returns. Each callback formats the text selected
during preparation. Empty requests return []. Do not modify requests. Keep
render_now(store, id, formatter) unchanged. Values are immutable strings.
