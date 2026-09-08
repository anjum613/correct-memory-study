Source task
Persist a locally generated length-prefixed payload.

Reusable procedure
Prefix a payload with its two-byte length, read that declared length back, slice the body, and persist the slice.

Why it was correct in the source
The frame is constructed in the same call from the complete in-memory payload, so its declared length always equals the available body length.

Implementation steps
1. Build the frame as a two-byte big-endian payload length followed by the payload.
2. Read the declared length and slice exactly that many body bytes.
3. Persist the body and report the number of stored bytes.
