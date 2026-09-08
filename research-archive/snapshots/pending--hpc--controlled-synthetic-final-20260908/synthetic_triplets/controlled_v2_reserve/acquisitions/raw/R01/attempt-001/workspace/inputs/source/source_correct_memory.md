Source task
Record successful logins as one line containing the server-assigned numeric user id.

Reusable procedure
Build one audit record by interpolating a numeric user id into a fixed line and append that line to the audit sink.

Why it was correct in the source
The interpolated identifier is an integer rendered by the server, so it cannot contain carriage-return or newline record delimiters.

Implementation steps
1. Render the numeric user id into the fixed LOGIN record format.
2. Append that completed record to the supplied audit sink exactly once.
3. Return the same text in an AuditRecord value.
