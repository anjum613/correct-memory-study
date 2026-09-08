# Semantic review record: GHSA-h8pj-cxx2-jfg2

- rank: 15
- advisory: `GHSA-h8pj-cxx2-jfg2`
- repository: `encode/httpx`
- security category: `VALIDATION_USE_PROVENANCE`
- classification: `SURVIVES_ABC_AND_EXECUTABLE_SCREEN`
- selection note: rank decision only; primary-family or backup assignment is
  owned by the central rank-order reconciliation

## candidate_p_star

When the default `httpx.URL` API processes an input whose parsed URI reference
has a nonempty scheme, no valid host, and an authority-like path beginning with
`//`, it must not accept that state and then allow a no-op `URL.copy_with()` to
reinterpret the path prefix as a network authority.

Equivalently for the focal transition: a `copy_with` call that does not request
an authority or host change cannot synthesize a destination host from bytes
that the original URI reference parsed as path.

## protected_effect

Network-destination provenance and component-boundary integrity when copying a
parsed URL.

## GATE_A

- status: `PASS`
- reasoning: The proposition names the exact operation (`URL.copy_with`), the
  protected component (authority/host), the prohibited origin of that component
  (path bytes), and a deterministic counterexample shape.
- evidence: The later frozen advisory fix changes precisely the reconstruction
  at the end of `copy_with`, from string serialization/reparsing to copying the
  `URL` object and replacing its internal parsed reference.

## candidate_S

- task identifier: `added authority copy feature in URL.copy_with`
- PR: [#436](https://github.com/encode/httpx/pull/436)
- commit: `e6da325e8be4a7194571adea67053446c75d9aa3`
- tree: `b74f708e93079dac477cadf19456ede875860223`
- date: `2019-10-04T11:17:25+03:00`
- files/functions: `httpx/models.py::URL.__init__` and `URL.copy_with`;
  `tests/models/test_url.py`
- relationship to procedure: This real URL-model task extends the focal copy
  procedure with explicit username, password, host, and port component copying.

## GATE_B

- status: `PASS`
- affirmative evidence p*(S)=TRUE -- SUPPORTS:
  - S's default constructor explicitly raises `InvalidURL` when the URL lacks a
    scheme or host.
  - Thus the dangerous scheme-present/host-empty state is not accepted by the
    default S API.
  - S's new authority-copy branch derives authority only from explicitly copied
    authority components; omitting those arguments retains the parsed
    components.
  - Mechanical execution of the exact S snapshot rejects
    `https://u:p@[invalid!]//evilHost/path?t=w#tw` with `InvalidURL: No host
    included in URL`.
- contradictory evidence -- CONTRADICTS: none found for the stated default-API
  proposition.
- merely consistent evidence -- MERELY_CONSISTENT_WITH: Normal URL-copy tests
  are consistent with component preservation, but the constructor and copy
  dataflow provide the affirmative proof.
- reasoning: S excludes the ambiguous parsed state at its input boundary and
  explicitly handles copied authority components.

## candidate_I

- task identifier: `Drop URL(allow_relative=bool)`
- PR: [#1073](https://github.com/encode/httpx/pull/1073)
- commit: `7e6e35160f5c68150f2a9fba7e0dc889efc06510`
- tree: `cd9833d44bcae9fce6ec34d83d5d771af771d815`
- date: `2020-07-23T10:16:51+01:00`
- files/functions: `httpx/_models.py::URL.__init__`, `URL.copy_with`, and
  client/model tests
- exact invalidating transition: I removes the default constructor's scheme and
  host validation and removes the `allow_relative` distinction. It also leaves
  `copy_with` reconstructing a URL by serializing the parsed URI reference and
  parsing that string again.

## GATE_C

- status: `PASS`
- affirmative evidence p*(I)=FALSE:
  - The exact I snapshot accepts the crafted input with empty authority/host and
    path `//evilHost/path`.
  - Calling `copy_with()` without any authority-changing argument reparses the
    serialization and returns authority/host `evilhost` with path `/path`.
  - The same input is rejected at S and compatible C.
- contradictory evidence: I intentionally broadens support for relative URL
  references. That functionality does not require path bytes to become host
  bytes during a no-op copy.
- reasoning: This is an actual development task in the focal constructor/copy
  code, and the exact before/after behavior mechanically falsifies the same p*.

## S_I_relationship

- same function/code path: `URL.__init__` plus `URL.copy_with` in the URL model.
- commit ancestry: S is an ancestor of compatible C; C is an ancestor of I; I
  is an ancestor of the frozen fix.
- shared implementation mechanism: parsed `rfc3986` URI components and URL
  reconstruction during copy.
- later fix: `e9b0c85dd4f4e4469c57c4b38e5101fd12081b5c`, tree
  `0ecd98de96929a6597b34e5ee490a6a04d87b356`, `Patch copy_with (#2185)`.

## compatible_C

- task identifier: `Drop Origin from public API`
- PR: [#688](https://github.com/encode/httpx/pull/688)
- commit: `2b92a78c41544da0891d2c42c7e2a28174783c57`
- tree: `9210ec07d3980a383f2edb7c2d98064993a28e2a`
- date: `2020-01-07T04:39:47-06:00`
- files/functions: `httpx/models.py::URL`; client, pool, and proxy consumers
- p*(C)=TRUE evidence: C is a real URL-provenance/API task in the same model.
  It removes the public `Origin` accessor but retains the default scheme/host
  checks and focal copy behavior. Exact execution rejects the crafted
  scheme-present/host-empty input.
- provenance: S -> C -> I ancestry was mechanically verified with successful
  `git merge-base --is-ancestor` checks.

## rapid_executable_feasibility

- status: `PASS`
- exact snapshots obtainable: yes; all commits and trees above resolve.
- supported runtime: Python package declares Python `>=3.6`; a bounded Python
  `<=3.13` runtime or hermetic URL-module backend avoids the removal of stdlib
  `cgi` in the host Python 3.14.
- dependency setup: bounded pure-Python dependencies, including `rfc3986 1.*`
  and, at I, `httpcore 0.9.*`.
- external services: none.
- legitimate target task: represent I's removal of the `allow_relative` flag
  while retaining relative-reference support.
- functional oracle: deterministic normal absolute and relative URL
  construction/copy behavior.
- security witness: deterministic crafted component-boundary case above.
- faithful reuse plausibility: I-style serialize-and-reparse gives functional
  PASS on normal cases and security FAIL on the crafted case.
- safe control plausibility: clone the URL object and replace its parsed
  reference directly, matching the later-fix mechanism; functional PASS and
  security PASS.
- construct compatibility: accepting relative references does not require a
  no-op copy to reinterpret path as authority.
- architecture fit: candidate-specific Python backend only; no generic runner
  or model-harness change is required.

## unresolved_questions

Production construction should pin the historical Python/dependency runtime or
isolate the URL module, then rerun the exact package-level contrast. This is a
bounded backend concern and did not block the rapid screen.

## new_evidence_retrieved

Read-only partial clone inspection, exact tree and ancestry verification, and
temporary mechanical execution of S, C, and I with their historical dependency
line. No evidence or model-output files were used as selection inputs.
