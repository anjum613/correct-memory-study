Source task
Deferred ordered report preparation

Reusable procedure
1. Validate every request and confirm all ids exist before opening leases.
2. Visit requests in order, acquiring a context-managed lease for each id.
3. Read the leased text, apply the supplied formatter, and wrap it with the request's prefix and suffix.
4. Return id/text/ordinal records while preserving duplicates and request order.

Why it was correct in the source
The source reads and formats every selected record before its lease exits; backing slots may be reused only later.
