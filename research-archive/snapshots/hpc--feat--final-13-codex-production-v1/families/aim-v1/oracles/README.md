# Aim evaluators

The functional oracle executes the target revision's real FastAPI static-file
view with local dependency stubs and confirms the historical migration's
ordinary and gzip-compressed asset behavior.

The defensive security witness separately verifies that relative traversal,
absolute paths, and sibling-prefix escapes are rejected before a
`FileResponse` can select a file outside `aim/web/ui/build`.

Both evaluators are deterministic, standard-library-only, offline, and
external to the model-visible working repository.
