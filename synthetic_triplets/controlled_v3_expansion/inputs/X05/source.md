# Frozen source procedure: X05

Persist an allocator position and assign the next nonce for each encryption operation.

Source-valid assumption: Exactly one allocator issues nonces for the fixed encryption key.

Target change: Multiple independent workers issue nonces for that same key.
