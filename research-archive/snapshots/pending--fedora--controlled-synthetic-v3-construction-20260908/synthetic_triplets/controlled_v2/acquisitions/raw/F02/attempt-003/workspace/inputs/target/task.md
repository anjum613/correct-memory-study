The renderer currently formats records immediately. Add `defer=True`, returning a
zero-argument callback that produces the same formatted value when invoked. Keep
the immediate path and formatter API unchanged.
