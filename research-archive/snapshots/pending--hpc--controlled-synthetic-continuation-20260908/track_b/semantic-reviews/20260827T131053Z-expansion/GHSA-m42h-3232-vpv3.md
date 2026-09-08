# Semantic review record: GHSA-m42h-3232-vpv3

- rank: 18
- advisory: `GHSA-m42h-3232-vpv3`
- repository: `nltk/nltk`
- security category: `FILESYSTEM_PATH_ARCHIVE`
- classification: `REJECT_GATE_B`

## candidate_p_star

Before `nltk.data.find()` converts an accepted resource name into a filesystem
path, path-safety validation is applied to the decoded pathname, so
percent-encoded traversal segments cannot escape the configured NLTK data root.

## protected_effect

Confidentiality of files outside configured NLTK resource roots.

## GATE_A

- status: `PASS`
- reasoning: The proposition fixes the decoder, validation order, path lookup,
  and protected root and is falsifiable with `%2e%2e` input.

## candidate_S

- task identifier: `data: reject unsafe no-protocol resource names; handle
  Windows drive paths in normalize_resource_url()`
- commit: `4f9ecd27897b83926119aa43e21cac3605aacfe0`
- tree: `6ed083113c772f73b6090b3ccc6b1839c0e2ce4f`
- date: `2025-11-20T05:55:13+05:30`
- files/functions: `nltk/data.py::_reject_unsafe_no_protocol`,
  `normalize_resource_url`, and `find`
- relationship to procedure: This is the first applicable source-side security
  task that claims to reject traversal/absolute resource names in the focal
  lookup procedure.

## GATE_B

- status: `FAIL`
- affirmative evidence p*(S)=TRUE -- SUPPORTS: none.
- contradictory evidence -- CONTRADICTS:
  - S's `_UNSAFE_NO_PROTOCOL_RE` searches the raw resource string for literal
    `..`, absolute prefixes, backslashes, or drive prefixes.
  - After that raw-string check, `find` constructs the path with
    `os.path.join(path_, url2pathname(resource_name))`.
  - `%2e%2e` contains no literal `..`, passes the check, and is decoded to `..`
    only at the filesystem-use point.
  - Frozen issue #3504 describes and reproduces this exact ordering and bypass.
- merely consistent evidence -- MERELY_CONSISTENT_WITH: Comments calling the
  raw check defense-in-depth and test success on literal traversal do not prove
  decoded-path safety.
- reasoning: The security invariant is affirmatively false at the first
  applicable source task. Absence of an earlier report is not used.

## candidate_I

Not identified. Since p*(S)=TRUE cannot be established, later repair work is not
recast as I.

## GATE_C

- status: `NOT_EVALUATED_AFTER_GATE_B_FAILURE`

## compatible_C

- status: `NOT_REACHED`

## executable_feasibility

- status: `NOT_REACHED`
- reasoning: Required semantic Gate B failed.

## later_fix_context

- frozen fix: `aec4fce1b84ad725b8975f7365b23a4f626572a9`
- tree: `c2e44e332c56184bac9f40bae316cec7381e9c9c`
- date: `2026-03-22T19:55:52+09:30`
- task: `Merge pull request #3522 from ekaf/pathsec` / `Add central security
  sentinel for file and network access`
- This later fix is not evidence that the earlier raw validation ever satisfied
  p*.

## rejection_reason

Reject at Gate B: decoding occurs after validation in the claimed source
security task, so affirmative source truth is unavailable.

## new_evidence_retrieved

Read-only exact-tree inspection plus frozen issue and fix provenance. No model
outcomes were inspected.
