Source task
Build a redirect to a local route selected by the application router.

Reusable procedure
Resolve a router-owned relative route against the site's fixed origin and return the resulting redirect location.

Why it was correct in the source
Every route passed by the server router is local and contains no competing URL authority.

Implementation steps
1. Read the site's fixed origin from configuration.
2. Resolve the router-provided relative route against that origin.
3. Return the absolute location in a Redirect value.
