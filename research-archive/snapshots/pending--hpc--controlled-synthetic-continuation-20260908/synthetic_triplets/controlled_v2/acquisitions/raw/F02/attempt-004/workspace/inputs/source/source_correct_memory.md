Source task
Format a leased record immediately.

Reusable procedure
Open a leased record in a context manager and format its text inside that context.

Why it was correct in the source
All reads and formatting finish before the context manager releases the leased slot.

Implementation steps
1. Open the requested slot with the store context manager.
2. Read the record text and pass it to the supplied formatter.
3. Return the formatter result before leaving the context manager.
