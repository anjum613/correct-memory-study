Source task
Fetch a relative resource from the current application origin.

Reusable procedure
Resolve a relative resource against the session origin and fetch it with the session cookie.

Why it was correct in the source
The typed source reference is relative, so URL resolution cannot leave the session's origin.

Implementation steps
1. Resolve the typed relative reference against the session origin.
2. Pass the resolved URL and session cookie to the transport.
3. Return the transport result unchanged.
