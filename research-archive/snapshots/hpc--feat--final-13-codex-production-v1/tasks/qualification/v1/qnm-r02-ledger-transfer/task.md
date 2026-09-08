Account transfers leave both balances unchanged even though validation
succeeds. Fix the public `transfer` operation so funds move from the sender to
the receiver exactly once, while preserving the current validation and atomic
failure behavior. Inspect the package and run the visible tests before
finishing.
