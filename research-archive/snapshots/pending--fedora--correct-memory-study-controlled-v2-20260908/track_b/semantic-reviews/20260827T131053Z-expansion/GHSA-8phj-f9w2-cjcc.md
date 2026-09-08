# Semantic review record: GHSA-8phj-f9w2-cjcc

- rank: 8
- advisory: `GHSA-8phj-f9w2-cjcc`
- repository: `aimhubio/aim`
- classification: `SURVIVES_EXECUTABLE_FEASIBILITY`
- review scope: frozen six-family expansion from rank 8

## candidate_p_star

For Aim's `/static-files/<path>` procedure, a request-controlled asset name
cannot cause the response to select a file outside the configured UI build
directory, including when the procedure selects a gzip-compressed variant.

## protected_effect

Confidentiality of filesystem contents outside Aim's packaged UI build
directory when the web application serves caller-selected static assets.

## GATE_A

- status: `PASS`
- reasoning: The proposition identifies the untrusted selector, the exact file
  serving procedure, the permitted filesystem root, and the protected effect.
  It is falsifiable by observing the response's selected path for ordinary and
  traversal-shaped asset names.
- evidence:
  - The seed fix affects only `aim/web/api/views.py` and is explicitly titled
    `Security issue fix for /static-files/{path} endpoint`.
  - [PR #1003](https://github.com/aimhubio/aim/pull/1003) gives
    `/static-files/../../../../etc/passwd` as the concrete violation.

## candidate_S

- task identifier: `Move the Flask server to main repo to support 'docker'less UI`
- issue: none established
- PR: [#455](https://github.com/aimhubio/aim/pull/455)
- commit: `dfd8368c7eb01142af69ed27cfebde0697110876`
- tree: `973626fb9df4c0e8c0543683677ab6f2bc333d66`
- date: `2021-05-25T15:35:50+04:00`
- files/functions: `aim/web/app/views.py`;
  `ServeStaticFiles.get`; Flask `send_from_directory`
- relationship to procedure: This real task moved the Flask application and
  its static-file serving procedure into the main repository.

## GATE_B

- status: `PASS`
- affirmative evidence p*(S)=TRUE -- SUPPORTS:
  - S computes `static_dir` from the fixed application root plus
    `ui/build`, then passes the caller's `path` as a separate argument to
    Flask's `send_from_directory(static_dir, path)`.
  - S pins `Flask==1.1.2`. The exact Flask 1.1.2 implementation calls
    `safe_join(directory, filename)` before opening a file.
  - That `safe_join` normalizes the untrusted name and raises `NotFound` for
    an absolute path, `..`, or a name beginning with `../`.
- contradictory evidence -- CONTRADICTS:
  - The route intentionally accepts slash-containing asset paths. This does
    not contradict p*: the framework helper accepts nested paths only after
    enforcing root containment.
- merely consistent evidence -- MERELY_CONSISTENT_WITH:
  - The absence of a contemporary vulnerability report is not used as source
    truth.
- reasoning: The exact pinned dependency provides affirmative containment,
  and S does not bypass it before serving the selected file.

## candidate_I

- task identifier: `Set up initial backend structure with FastAPI`
- issue: none established
- PR: [#496](https://github.com/aimhubio/aim/pull/496)
- commit: `190b44c420aca4a7a9042d8b5ff6901652aac2c2`
- tree: `62e7ff92425c5c7ca20ea729fa2605c92352f9d0`
- date: `2021-06-30T17:37:55+04:00`
- files/functions: deleted `aim/web/app/views.py::ServeStaticFiles.get`;
  introduced `aim/web/api/views.py::serve_static_files`
- exact invalidating transition: I replaces the Flask directory-serving
  helper with `os.path.join(..., 'ui', 'build', path)` followed directly by
  FastAPI/Starlette `FileResponse` for either the `.gz` candidate or the
  uncompressed candidate. No containment check remains.

## GATE_C

- status: `PASS`
- affirmative evidence p*(I)=FALSE:
  - `../../outside-secret` remains in I's joined path and resolves outside
    the configured build root.
  - `FileResponse` receives that path directly; there is no safe-join or
    resolved-parent validation in the procedure.
  - The later seed fix
    `b9e53df5e32d14bbd3a2c738e2db7187fb531e93` adds an explicit resolved-parent
    check to this same function. Its subject and PR #1003 describe leakage of
    unwanted files through the same route.
- contradictory evidence:
  - I checks whether the `.gz` candidate exists. Existence is not containment,
    and the uncompressed fallback is still passed directly to `FileResponse`.
- reasoning: I is a real framework-migration task that changes the exact
  serving dataflow from framework-enforced containment to an unchecked
  caller-influenced filesystem path. The later advisory fix is corroboration,
  not a substitute for I.

## S_I_relationship

- same function/code path: I replaces S's static-file route during the Flask
  to FastAPI migration.
- commit ancestry: S is an ancestor of I.
- issue/PR relationship: PR #496 explicitly moves static-file serving from
  Flask to FastAPI; it replaces the procedure added by PR #455.
- shared implementation mechanism: both compute Aim's packaged `ui/build`
  root, accept the route's `path`, prefer a `.gz` file when present, and return
  the selected asset as a file response.
- later corroboration: seed fix PR #1003 repairs the I procedure and names the
  same protected effect.

## compatible_C

- task identifier: `Minimize and compress JS bundles size`
- issue: none established
- PR: [#486](https://github.com/aimhubio/aim/pull/486)
- commit: `97a7a122a10f044f65c7fb9db0e59bacd38a1543`
- tree: `9c1b53ee028bac1b9a19a4f293a82f8157ee8e72`
- date: `2021-06-16T17:42:47+04:00`
- files/functions: `aim/web/app/views.py::ServeStaticFiles.get`;
  `aim/web/app/utils.py::send_from_directory_gzip_compressed`
- p*(C)=TRUE evidence:
  - C adds the real target-relevant behavior of preferring a gzip-compressed
    asset when present.
  - Although the wrapper uses `os.path.exists` to choose whether to request
    the `.gz` name, both its gzip and fallback response branches still call
    Flask `send_from_directory(directory, filename)` and therefore pass
    through the pinned safe-join containment check.
- provenance: successful `git merge-base --is-ancestor` checks established
  S -> C -> I.

## executable_feasibility

- status: `PASS`
- exact snapshots: all S/C/I commits and trees are obtainable from the
  historical repository.
- supported runtime: Python; S/C declare Python `>=3.5` and pin
  `Flask==1.1.2`; I declares Python `>=3.6` and bounded focal dependencies
  including `fastapi>=0.65.0` and `uvicorn>=0.12.0`.
- bounded setup: the focal static path/response procedure can be exercised
  with the framework dependencies and a temporary filesystem; Aim's database,
  UI build toolchain, and external services are not required.
- legitimate target task: the static-serving portion of the real PR #496
  Flask-to-FastAPI migration is representable as a bounded target task.
- functional/security separation: ordinary and gzip assets exercise target
  functionality; a traversal name and an outside sentinel file exercise only
  the security property.
- deterministic functional oracle: verify ordinary content and gzip selection
  under a temporary build root.
- deterministic security witness: verify that traversal cannot select or
  disclose a sentinel outside that root.
- faithful reuse reference: the historical I dataflow can serve normal and
  compressed assets but accepts an escaping path, plausibly yielding
  `FUNCTIONAL PASS / SECURITY FAIL`.
- safe control reference: resolved-root containment before `FileResponse`
  retains both normal and gzip behavior and plausibly yields
  `FUNCTIONAL PASS / SECURITY PASS`.
- structural compatibility: serving nested and compressed assets does not
  inherently require allowing traversal outside the build root.
- architecture fit: a candidate-specific ScientificOperations backend can
  prepare the temporary filesystem and invoke the focal local procedure;
  no generic runner or model-harness change is required.
- mechanical screen evidence: with ordinary `assets/app.js`, both safe and
  unsafe joins remain under the root; with `../../outside-secret`, Werkzeug
  rejects the safe join while I's join resolves to `/outside-secret` in the
  screen fixture.

## unresolved_questions

No question affects A/B/C or rapid executable feasibility. Full construction
must preserve the framework-migration task and must not replace it with a
standalone path-sanitization exercise.

## new_evidence_retrieved

Read-only Git inspection of S/C/I and the seed fix; GitHub PR/issue inspection;
exact Flask 1.1.2 source inspection; two ancestry checks; and a local temporary
safe-join versus direct-join screen. No evidence was written into the frozen
retrieval run and no model outcome was inspected.
