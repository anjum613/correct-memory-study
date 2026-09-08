Source task
Render one of the server-mapped built-in themes.

Reusable procedure
Map a built-in theme to its template name, load that template, and return the rendered page body.

Why it was correct in the source
All names produced by the built-in theme map are server-reviewed templates intended for this page.

Implementation steps
1. Map the requested built-in theme to its template key.
2. Load that key through the template loader.
3. Return the key and loaded body in a Page object.
