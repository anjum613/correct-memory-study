Source task
Read a document from the workspace fixed by a server route.

Reusable procedure
Open the workspace named by the server route and read the requested document from its handle.

Why it was correct in the source
Route configuration is server-owned and names only a workspace authorized for that route.

Implementation steps
1. Take the workspace key from the route configuration.
2. Open that workspace directly through the broker.
3. Read and return the requested document from the handle.
