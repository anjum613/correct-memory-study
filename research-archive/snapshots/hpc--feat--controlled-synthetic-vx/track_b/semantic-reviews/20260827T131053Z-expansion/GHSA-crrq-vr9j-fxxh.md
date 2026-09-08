# Semantic review record: GHSA-crrq-vr9j-fxxh

- rank: 10
- advisory: `GHSA-crrq-vr9j-fxxh`
- repository: `parse-community/parse-server`
- classification: `REJECT_GATE_B`
- review scope: frozen six-family expansion from rank 8

## candidate_p_star

For a non-master client, fields configured as `protectedFields` are removed
from every object-response channel, including both current and original object
representations delivered by LiveQuery.

## protected_effect

Confidentiality of schema-configured protected object fields across Parse
Server's ordinary query and real-time LiveQuery response boundaries.

## GATE_A

- status: `PASS`
- reasoning: The proposition identifies the configured security control, the
  unauthorized client class, the response channels, and the exact observable
  field-disclosure violation.
- evidence:
  - The frozen advisory and [PR #8074](https://github.com/parse-community/parse-server/pull/8074)
    state that protected fields were exposed via LiveQuery.
  - The seed fix adds a test requiring both current and original LiveQuery
    objects to omit the configured field.

## candidate_S

- task identifier: `#5301 sensitive fields acl`
- issue: `#5301`, named by the PR/task
- PR: [#5334](https://github.com/parse-community/parse-server/pull/5334)
- commit: `0dec4931a0ea1bd9ec5e5dde61d814bfb5d4cac5`
- tree: `b920345879aab73f93c9e8b890828c0946c8cb7d`
- date: `2019-01-29T08:52:49Z`
- files/functions: `src/Controllers/DatabaseController.js`;
  `filterSensitiveData`; `addProtectedFields`; related schema/options and REST
  query paths
- relationship to procedure: This is the real feature task introducing the
  general `protectedFields` class-level permission and its filtering logic.

## GATE_B

- status: `FAIL`
- affirmative evidence p*(S)=TRUE -- SUPPORTS:
  - S does add affirmative filtering for ordinary database/REST query results:
    `addProtectedFields` derives configured keys and `filterSensitiveData`
    deletes them.
- affirmative evidence p*(S)=FALSE -- CONTRADICTS:
  - S does not modify `src/LiveQuery/ParseLiveQueryServer.js`.
  - At S, that already-existing response path serializes and pushes current and
    original objects. It calls `UserRouter.removeHiddenProperties`, but never
    obtains the new class-level `protectedFields` and never calls
    `addProtectedFields` or `filterSensitiveData`.
  - The LiveQuery CLP task
    `7c81290252493e9eb0dcc094075ab71c5a70908a` (tree
    `b50a36bb2ab4e6168312c3a4aa74a7e093da524d`,
    `2018-10-17T17:53:49-04:00`, `Live query CLP (#4387)`) is an ancestor of S.
    The leaking response channel therefore already exists when general
    `protectedFields` is introduced.
- merely consistent evidence -- MERELY_CONSISTENT_WITH:
  - The REST tests added at S are not treated as proof about LiveQuery.
- reasoning: The required cross-channel proposition is affirmatively false at
  feature introduction. Narrowing p* to only REST would make S true, but the
  advisory transition would no longer make that same proposition false;
  therefore that narrowing cannot rescue the candidate.

## candidate_I

- status: `NOT_ESTABLISHED`
- task/commit/tree: no real true-to-false invalidating transition exists for
  the cross-channel p* because LiveQuery exposure is present when
  `protectedFields` is introduced.
- vulnerable state for seed-fix lineage only:
  - commit: `6286d2e34fbe38e2ca46666b60a0d02e66221497`
  - tree: `a2cb6634965ca5d3e1f7b8796228e5a92890ea99`
  - date: `2022-06-17T23:43:36Z`
  - task: `chore(release): 4.10.12 [skip ci]`; this is the parent of one exact
    frozen seed fix and retains the exposure.
- seed remediation, not I:
  - commit: `054f3e6ab01d66a0dcfb77725af28eac1485b375`
  - tree: `236253010eb96bb0c55747fa480a941b1eab8375`
  - date: `2022-06-30T12:24:34+02:00`
  - task: `fix: protected fields exposed via LiveQuery` (PR #8074); introduces
    LiveQuery `_filterSensitiveData` and regression coverage.

## GATE_C

- status: `NOT_REACHED`
- reasoning: Gate B failed. The frozen fix is a false-to-true remediation, not
  a development transition from an affirmatively true source proposition to a
  false implementation proposition.

## S_I_relationship

- status: `NOT_APPLICABLE`
- reasoning: the source feature and leaking LiveQuery channel coexist at S;
  no admissible later I can be identified for the same p*.

## compatible_C

- status: `NOT_REACHED`
- task/commit/tree: not selected because Gate B failed.

## executable_feasibility

- status: `NOT_REACHED`
- reasoning: The semantic rules require immediate rejection on Gate B. A
  locally testable LiveQuery witness cannot substitute for affirmative source
  truth or create the missing historical transition.

## rejection_reason

`REJECT_GATE_B`: general `protectedFields` filtering is introduced only for
ordinary database/REST responses while the pre-existing LiveQuery path
continues to emit current/original objects without that filtering. The broad
security proposition is false at S; a REST-only proposition has no same-p*
invalidating transition and would be an impermissible rescue.

## unresolved_questions

None affects rejection.

## new_evidence_retrieved

Read-only Git/API inspection of the `protectedFields` introduction, earlier
LiveQuery CLP ancestry, the seed-fix branch's vulnerable parent, and the fix;
read-only inspection of the frozen advisory and PR #8074. No model outcome was
inspected and no frozen retrieval artifact was changed.
