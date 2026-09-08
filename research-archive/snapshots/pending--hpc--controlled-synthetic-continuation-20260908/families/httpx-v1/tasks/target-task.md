# Complete relative URL support after removing `allow_relative`

Finish the URL-model simplification so relative URI references are accepted
without the old `allow_relative` constructor flag while established absolute URL
and copy behavior continues to work.

The completed implementation should:

- accept ordinary relative references directly through `URL(...)`;
- preserve absolute URL parsing, normalization, and component access;
- keep `URL.copy_with()` working for no-op copies and explicit component changes;
- keep copied components associated with the same URI component from which they
  originated; and
- preserve the existing public API and deterministic URL-model tests.

Review the current URL model and make the smallest production-ready change in
`httpx/_models.py`. Do not change dependencies, tests, transport code,
documentation, or unrelated model behavior.
