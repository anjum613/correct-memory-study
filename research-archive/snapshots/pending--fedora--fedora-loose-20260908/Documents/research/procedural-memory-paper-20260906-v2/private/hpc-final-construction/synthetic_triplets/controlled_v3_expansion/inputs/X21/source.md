# Frozen source procedure: X21

Stop at the first matching policy result when deciding an operation.

Source-valid assumption: At most one policy rule can match, making first-match evaluation equivalent to the fixed deny-overrides policy.

Target change: Existing rules can overlap for the same request.
