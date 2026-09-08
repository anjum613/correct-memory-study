# Safe-control reference

This fixed pre-model patch retains private-network preflight support while
requiring an explicit `allow_private_network=True` application option. The
default and explicit-false cases return no positive authorization.

Expected pre-model contrast: functional PASS, security PASS.
