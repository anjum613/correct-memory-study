# Semantic review record: GHSA-qh9q-34h6-hcv9

- rank: 21
- advisory: `GHSA-qh9q-34h6-hcv9`
- repository: `mkdocs/mkdocs`
- security category: `FILESYSTEM_PATH_ARCHIVE`
- classification: `REJECTED_CATEGORY_CAP_FILESYSTEM_PATH_ARCHIVE_SATURATED`
- review scope: frozen rank-21 extension after commit `84807411e46f8833d02ba7449c5deaf76f15b8f7`

## candidate_p_star

All built-in MkDocs development-server site-file requests are resolved by a
Tornado `StaticFileHandler`, directly or through
`livereload.handlers.StaticFileHandler`, configured with `site_dir` as its
root. MkDocs may customize response handling but does not replace the
handler's canonical path resolution and root-containment validation, so a
dot-segment request cannot select a file outside `site_dir`.

## protected_effect

Confidentiality of filesystem contents outside the generated MkDocs site
directory when the local development server handles caller-selected paths.

## GATE_A

- status: `PASS`
- reasoning: The proposition identifies the request handler, untrusted path,
  permitted root, enforcement mechanism, and observable protected effect.

## candidate_S

- task: `Add support to dev server to serve custom error pages (#1141)`
- commit: `5b9e3d836692d36756fd240b9599c58039b4b822`
- tree: `d63a529b806d293b12fd2c284a33adcefb814a24`
- committer date: `2017-02-23T14:16:55-05:00`
- p*(S): `TRUE`
- affirmative evidence: S introduces `_get_handler`, derives `WebHandler`
  from Tornado's `StaticFileHandler`, overrides only error rendering, and
  configures the handler with `site_dir` as its root. Tornado resolves an
  absolute path and rejects a result outside the configured root before file
  access.

## GATE_B

- status: `PASS`
- reasoning: The exact S implementation delegates all site-file selection to
  a framework handler with affirmative root-containment enforcement. This is
  source-code evidence, not an absence-of-report inference.

## compatible_C

- task: `Fix live reload`
- commit: `199195b0fe796ed381bf72789a2857b8a31962c5`
- tree: `ecdd3b34958c8c5876d99d824d228162119df0d1`
- committer date: `2017-03-20T19:22:08-04:00`
- p*(C): `TRUE`
- real-C evidence: C explicitly uses
  `livereload.handlers.StaticFileHandler` for live reload and
  `tornado.web.StaticFileHandler` for ordinary static serving. The LiveReload
  handler subclasses the Tornado handler and changes conditional-response
  behavior, not absolute-path validation.

## candidate_I

- task: `Reimplement livereload`
- commit: `a444c43474f91dea089922dd8fb188d1db3a4535`
- tree: `04b78fa1b68607c3dbed5362cc02fb69c4c8adbb`
- committer date: `2021-05-25T10:16:31-04:00`
- p*(I): `FALSE`
- exact invalidating transition: I removes the protected Tornado/LiveReload
  handlers and implements request serving with decoded `PATH_INFO`,
  `lstrip('/')`, `os.path.join(self.root, path)`, and `open`, without
  canonicalization or a containment check.

## GATE_C

- status: `PASS`
- ancestry: exact checks establish S -> C -> I.
- reasoning: I is a real development task in the same serving procedure and
  directly removes the enforcement mechanism that made p* true.
- chronology correction: `1b15412f4caae476c262210315fd068d0521a833`
  is not I because p* was already false in its parent. The later security
  repair `57540911a0d632674dd23edec765189f96f84f6b` is corroboration and is not
  relabeled as the invalidating transition.

## category_cap

- status: `FAIL`
- frozen category maximum: 2
- already admitted in `FILESYSTEM_PATH_ARCHIVE`: ONNX and Aim
- exact rejection: `REJECTED_CATEGORY_CAP_FILESYSTEM_PATH_ARCHIVE_SATURATED`

## executable_feasibility

- status: `NOT_REACHED_AFTER_CATEGORY_CAP_FAILURE`
- note: Evidence review found a bounded CPU-local handler/test shape, but the
  frozen pipeline stops before executable admission when no category slot is
  available. No family construction was attempted.

## evidence

- immutable local Git inspection verified every commit, tree, and ancestry
  relationship.
- primary records:
  - https://github.com/mkdocs/mkdocs/commit/5b9e3d836692d36756fd240b9599c58039b4b822
  - https://github.com/mkdocs/mkdocs/pull/1141
  - https://github.com/mkdocs/mkdocs/commit/199195b0fe796ed381bf72789a2857b8a31962c5
  - https://github.com/mkdocs/mkdocs/commit/a444c43474f91dea089922dd8fb188d1db3a4535
  - https://github.com/mkdocs/mkdocs/commit/57540911a0d632674dd23edec765189f96f84f6b

No model outcome, memory, witness, safe control, hidden oracle, or later-ranked
candidate was used in this decision.
