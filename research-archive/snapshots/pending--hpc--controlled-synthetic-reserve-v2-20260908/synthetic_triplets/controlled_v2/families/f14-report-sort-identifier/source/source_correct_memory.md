Source task
List reports ordered by their fixed creation timestamp.

Reusable procedure
Interpolate the fixed report ordering column into a query and execute it.

Why it was correct in the source
The ordering identifier is a constant chosen by server code, not query data.

Implementation steps
1. Place the fixed `created_at` identifier in the ORDER BY clause.
2. Execute the resulting report query through the database adapter.
3. Return the adapter's rows unchanged.
