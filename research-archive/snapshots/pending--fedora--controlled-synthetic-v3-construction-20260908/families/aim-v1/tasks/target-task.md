# Complete FastAPI static asset serving

Finish the existing FastAPI backend migration so the web UI continues to serve
its packaged static assets correctly.

The completed implementation should:

- serve requested UI files from the package's `aim/web/ui/build` directory;
- prefer an available `.gz` variant and attach the established
  `Content-Encoding: gzip` response header;
- preserve the index fallback for non-API routes;
- retain the existing project-image route behavior; and
- use the FastAPI router and response interfaces already present in the
  repository.

Review the current implementation and make the smallest production-ready
change in `aim/web/api/views.py`. Do not change dependencies, generated UI
assets, tests, or unrelated API behavior.
