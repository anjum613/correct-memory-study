# Semantic review record: GHSA-9x43-5qcq-h79q

- rank: 9
- advisory: `GHSA-9x43-5qcq-h79q`
- repository: `sehmaschine/django-grappelli`
- classification: `REJECT_GATE_B`
- review scope: frozen six-family expansion from rank 8

## candidate_p_star

The `switch_user` view may redirect a staff user only to a same-origin URL
allowed for the current request host and scheme; caller-controlled redirect
input cannot select an external network destination.

## protected_effect

Navigation integrity and same-origin trust after the privileged switch-user
operation.

## GATE_A

- status: `PASS`
- reasoning: The proposition identifies the privileged view, the
  caller-controlled value, the exact destination constraint, and an observable
  violation.
- evidence:
  - Frozen seed issue [#975](https://github.com/sehmaschine/django-grappelli/issues/975)
    gives `?redirect=//example.com` as a concrete external redirect.
  - The seed fix changes only `grappelli/views/switch.py` and introduces
    Django's host-and-scheme validator for this value.

## candidate_S

- task identifier: `switch user draft, #393`
- issue: `#393` is named by the commit; issue contents were not needed for the
  decision
- PR: none established
- commit: `03e15e34b01ec20409e6466f5ed186a583370b0d`
- tree: `b5d730a1462c3a900f422c0b165590c21386efcf`
- date: `2013-11-08T14:20:26+01:00`
- files/functions: `grappelli/views/switch.py::switch_user`
- relationship to procedure: This is the first repository commit introducing
  the focal switch-user view and its redirect behavior.

## GATE_B

- status: `FAIL`
- affirmative evidence p*(S)=TRUE -- SUPPORTS:
  - none
- affirmative evidence p*(S)=FALSE -- CONTRADICTS:
  - S passes `request.GET.get("redirect")` directly to Django `redirect` in
    every completion/error branch, with no host, scheme, or origin validation.
  - Therefore an external destination is selectable at the procedure's
    inception.
  - Commit `022f67d2f7f17a625c7de3a56982a38cb521d60b`
    (`fixed redirect check with switch user`, tree
    `1462d7997c42ee57955f616acc14519adcdf5a2e`,
    `2021-03-22T15:47:34+01:00`) later requires only
    `redirect_url.startswith("/")`. The issue's `//example.com` input passes
    that check, so this attempted check also does not establish p*.
- merely consistent evidence -- MERELY_CONSISTENT_WITH:
  - No absence-of-report evidence is used.
- reasoning: There is affirmative source evidence that the same proposition
  was false at the real feature introduction and remained false after the
  intermediate prefix check. Absence of the view before S cannot establish
  source truth.

## candidate_I

- status: `NOT_ESTABLISHED`
- task/commit/tree: no real true-to-false invalidating transition exists
  because the required proposition was already false at candidate S.
- advisory-vulnerable state for provenance only:
  - commit: `55f88d661c28598d059cf81dbfd38dacb945662f`
  - tree: `8134c838222a9a842ac21311a3b561a551425633`
  - date: `2021-08-04T13:28:42+02:00`
  - task: merge PR #972; it retains the insufficient `startswith("/")` check
    identified by issue #975.
- seed remediation, not I:
  - commit: `4ca94bcda0fa2720594506853d85e00c8212968f`
  - tree: `e1d8e3a5510c1be82683c07611479adea3859b9c`
  - date: `2021-09-30T20:39:12+09:00`
  - task: `Update switch.py`; adds
    `url_has_allowed_host_and_scheme` and changes p* from false to true.

## GATE_C

- status: `NOT_REACHED`
- reasoning: Gate B failed. The seed fix is a false-to-true remediation, not a
  historical development transition in which an affirmatively true p* becomes
  false. It cannot be relabeled as I.

## S_I_relationship

- status: `NOT_APPLICABLE`
- reasoning: no admissible I exists after the Gate B failure.

## compatible_C

- status: `NOT_REACHED`
- task/commit/tree: not selected because Gate B failed.

## executable_feasibility

- status: `NOT_REACHED`
- reasoning: The semantic rules require immediate rejection when a required
  gate fails. Runtime or witness convenience cannot rescue absent affirmative
  p*(S)=TRUE evidence.

## rejection_reason

`REJECT_GATE_B`: the same-origin redirect proposition is affirmatively false
when `switch_user` is introduced, and the later prefix check remains bypassable
by the exact `//example.com` form documented in the frozen issue. The only
established true state is the later advisory remediation; there is no eligible
true-to-false transition.

## unresolved_questions

None affects rejection.

## new_evidence_retrieved

Read-only Git history, blame, commit/tree, and ancestry inspection for the
initial view, intermediate prefix check, issue-referenced vulnerable state,
and seed fix; read-only inspection of issue #975. No model outcome was
inspected and no frozen retrieval artifact was changed.
