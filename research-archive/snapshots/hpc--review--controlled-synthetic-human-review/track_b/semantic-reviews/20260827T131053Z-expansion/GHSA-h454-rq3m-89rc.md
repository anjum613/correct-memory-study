# Semantic review record: GHSA-h454-rq3m-89rc

- rank: 14
- advisory: `GHSA-h454-rq3m-89rc`
- repository: `coderedcorp/coderedcms`
- classification: `REJECTED_GATE_B`
- time_spent: approximately 20 minutes

## candidate_p_star

An authenticated protected-media request can read only a file contained within
the configured `PROTECTED_MEDIA_ROOT` directory.

## protected_effect

Confidentiality of process-readable files outside the protected-media root.

## GATE_A

- status: `PASS`
- reasoning: The proposition fixes one route, one filesystem root, and one
  containment effect and is falsifiable with a traversal path and an external
  sentinel file.
- evidence:
  - The initial view and URL route are in
    [`coderedcms/views.py`](https://github.com/coderedcorp/coderedcms/blob/46dda3eed21e9f8d8a92d0f8d48a575ecf91636c/coderedcms/views.py)
    and
    [`coderedcms/urls.py`](https://github.com/coderedcorp/coderedcms/blob/46dda3eed21e9f8d8a92d0f8d48a575ecf91636c/coderedcms/urls.py).
  - The frozen fix explicitly adds root containment for the same protected-file
    operation.

## attempted_candidate_S

- task identifier: `Adding project to github`
- issue: none
- PR: none
- commit: `46dda3eed21e9f8d8a92d0f8d48a575ecf91636c`
- tree: `f562e1e45d76e50864d0b05efdb72208a044d9c2`
- date: `2018-07-31T15:36:47-04:00`
- files/functions: `coderedcms/urls.py`; protected-media URL pattern;
  `coderedcms/views.py::serve_protected_file`
- relationship to procedure: This initial repository commit already contains
  the complete focal protected-media route and file-serving view.

## GATE_B

- status: `FAIL`
- affirmative evidence p*(S)=TRUE -- SUPPORTS:
  - None. No implemented protected-file-serving source state with affirmative
    root containment predates the vulnerable implementation.
- contradictory evidence -- CONTRADICTS:
  - The initial URL regex captures arbitrary remaining text with
    `(?P<path>.*)` after the protected-media prefix.
  - The initial view computes only
    `os.path.join(PROTECTED_MEDIA_ROOT, path)`, checks `os.path.isfile`, and
    opens the result.
  - It performs no absolute-path resolution, normalization, common-path check,
    or other containment validation.
  - Blame confirms the vulnerable route and view originate in the first
    repository commit and persist to the security fix.
- merely consistent evidence -- MERELY_CONSISTENT_WITH:
  - The `login_required` decorator restricts who can call the route but does
    not constrain which process-readable file an authenticated caller selects.
  - Absence of repository history before the initial commit is not evidence of
    p*(S)=TRUE.
- reasoning: The focal proposition is false at the earliest available
  historical implementation. Only a later FALSE -> TRUE fix exists.

## candidate_I

- status: `NOT_ESTABLISHED_AFTER_GATE_B_FAILURE`
- reasoning: The vulnerable code is present in the initial commit; there is no
  real earlier source implementation from which a same-p* invalidating
  transition can be identified.

## GATE_C

- status: `NOT_REACHED`
- reasoning: Gate B failed. The security fix cannot substitute for a historical
  development transition that makes a previously true proposition false.

## compatible_C

- status: `NOT_REACHED`
- reasoning: Compatible C is considered only after A/B/C survive.

## rapid_executable_feasibility

- status: `NOT_REACHED`
- reasoning: The candidate was rejected at Gate B and was not rescued through
  executable considerations.

## rejection_reason

`GATE_B_NO_AFFIRMATIVE_SOURCE_TRUTH_VULNERABLE_IN_INITIAL_COMMIT`

## exact_fix_context

- fix task: `Prevent upward path traversals when serving protected media (#450)`
- fix PR: [#450](https://github.com/coderedcorp/coderedcms/pull/450)
- fix commit: `06006cec23a723bc7d76df75ce2c2d795a447902`
- fix tree: `6d29b3a851effe93b75273910c99654b51b56974`
- fix date: `2021-09-29T16:13:13-04:00`
- fix behavior: resolve the media root and joined path with `abspath`, then
  require the result to begin with the media root before opening it.
- ancestry: initial commit -> fix was mechanically verified.

## unresolved_questions

None that justify continued review. Recasting authentication itself as p*
would abandon the advisory's filesystem-containment protected effect and was
not used as a rescue.

## new_evidence_retrieved

Read-only filtered clone, initial-commit inspection, blame, fix diff inspection,
and ancestry verification. No model outcomes were inspected.
