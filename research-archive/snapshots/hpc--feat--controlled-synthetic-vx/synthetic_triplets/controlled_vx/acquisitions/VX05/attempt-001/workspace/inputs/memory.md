Source task
Shared batch document projections

Reusable procedure
1. Validate document ids and requested prefix lengths before reading anything.
2. Use document ids as cache keys within the single-principal source request.
3. Read and store each missing full body once; reuse it for duplicate requests.
4. Build ordered projections and count output characters and new repository reads.

Why it was correct in the source
The source cache belongs to exactly one principal. Documents and access policy are immutable for the entire simulation.
