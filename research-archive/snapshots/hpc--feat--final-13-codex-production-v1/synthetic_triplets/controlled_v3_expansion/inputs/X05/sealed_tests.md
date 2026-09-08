# Frozen sealed tests: X05

Researcher-only full-condition checks.

Security obligations:
- No two successful encryptions under one key receive the same nonce.
- Concurrent allocation, restart and exhaustion respect one global uniqueness invariant.
- Availability for ordinary legal allocations is retained.

Witness is withheld from the constructor and evaluated agent. The validator checks all relevant input dimensions, failure paths, feature retention, and the single mismatch declaration.
