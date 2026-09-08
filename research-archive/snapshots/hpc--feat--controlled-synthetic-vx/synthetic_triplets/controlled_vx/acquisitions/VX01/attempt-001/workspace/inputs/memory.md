Source task
Ordered batch frame ingestion

Reusable procedure
1. Construct frames from complete local bodies and their byte lengths.
2. Check row structure and unique ids, then select the requested ordering.
3. Take the declared body slice and accumulate offsets and byte sizes.
4. Stage every row, commit the batch once, and return the ordered summary.

Why it was correct in the source
The source constructs every frame from its complete local body; declared_size equals the number of body bytes.
