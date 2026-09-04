Add `shared=True` support to `get_document` so callers can pass the application's
long-lived cache instead of a request-local dictionary. Preserve cache hits,
repository access, return values, and the existing local mode.
