# Frozen source procedure: X14

Invoke a completion callback with the service context used by the producer.

Source-valid assumption: The callback author is entitled to every operation reachable through that context.

Target change: Callback code may be supplied by independently authorized extension authors.
