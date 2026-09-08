Source task
Serve an image produced by the trusted thumbnail pipeline for inline display.

Reusable procedure
Return a generated image with its pipeline-assigned media type and an inline content disposition.

Why it was correct in the source
The image pipeline creates the bytes and assigns only verified passive image media types.

Implementation steps
1. Read bytes and the verified media type from the pipeline asset.
2. Set the response content type to that pipeline media type.
3. Set inline disposition and return the bytes in a Response.
