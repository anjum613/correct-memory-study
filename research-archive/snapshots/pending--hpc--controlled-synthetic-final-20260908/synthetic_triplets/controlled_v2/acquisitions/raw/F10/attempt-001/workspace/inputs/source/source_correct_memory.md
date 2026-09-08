Source task
Fetch a relative endpoint from the fixed internal integration.

Reusable procedure
Resolve a relative resource reference against the fixed integration base and fetch the resulting URL.

Why it was correct in the source
The integration base URL is fixed by server configuration to an authorized origin.

Implementation steps
1. Resolve the relative reference against the configured integration base with URL joining.
2. Pass the resulting absolute URL to the transport.
3. Return the transport response unchanged.
