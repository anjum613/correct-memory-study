Source task
Load a router-canonical resource from the safe namespace.

Reusable procedure
Check the safe namespace prefix on a canonical path and then read that exact path.

Why it was correct in the source
The router supplies a CanonicalResourcePath whose constructor rejects non-normalized paths before the service sees them.

Implementation steps
1. Receive the router's CanonicalResourcePath value.
2. Require its value to begin with the `/safe/` namespace prefix.
3. Read that same path from the resource store and return the resource.
