# Semantic review record: GHSA-7gwp-5pfp-969j

- rank: 4
- advisory: `GHSA-7gwp-5pfp-969j`
- repository: `mlflow/mlflow`
- classification: `REJECT_B_SOURCE_NOT_PROVEN_TRUE`
- time_spent: approximately 16 minutes

## candidate_p_star

For every webhook delivery, the actual connected destination used by
`session.post(webhook.url)` is the same public/global destination established
as safe by `_validate_webhook_url`.

## protected_effect

Prevent the MLflow server's webhook-delivery authority from reaching private,
loopback, link-local, or internal network destinations.

## GATE_A

- status: `PASS`
- reasoning: The proposition names the guard, the protected outbound operation,
  and the exact connection-time destination invariant.
- evidence:
  - Frozen pre-fix blame places `_validate_webhook_url(webhook.url)` immediately
    before delivery in
    `raw/GHSA-7gwp-5pfp-969j/git-history/mlflow__mlflow__mlflow__webhooks__delivery.py__blame.txt`.
  - Frozen fix patch `ba949522477cbd5915aa55d29b0cfad7d5ddf939`
    identifies validation of the actual connected peer as the missing invariant.

## candidate_S

- task identifier: `Validate webhook url to fix SSRF vulnerability`
- issue: [#20704](https://github.com/mlflow/mlflow/issues/20704)
- PR: [#20747](https://github.com/mlflow/mlflow/pull/20747)
- commit: `64aa0ab7207f9c649b59ba1a5f40d82196817389`
- date: `2026-02-13T16:49:29+09:00`
- files/functions: `mlflow/utils/validation.py::_validate_webhook_url`;
  `mlflow/webhooks/delivery.py::_send_webhook_request`
- relationship to procedure: This is the natural source task because it added
  the destination validator immediately before the same webhook delivery path.

## GATE_B

- status: `FAIL`
- affirmative evidence p*(S)=TRUE -- SUPPORTS: none. PR #20747 establishes the
  intent to validate destinations, but not that the actual connection uses the
  already validated address.
- contradictory evidence -- CONTRADICTS:
  - At S, `_validate_webhook_url` resolves and checks the hostname but discards
    that result.
  - The pre-existing `session.post(webhook.url)` remains and independently
    selects the connection destination later.
  - Frozen issue #24179 and the fix patch explicitly state that this gap exists
    in the #20747 implementation itself; no later feature task invalidated it.
  - Before #20747, initial webhook PR #16583 performed the outbound request
    without destination validation, so that earlier state cannot establish p*.
- merely consistent evidence -- MERELY_CONSISTENT_WITH:
  - PR #20747's title, intended security goal, and tests are consistent with
    maintainers expecting safe destinations.
  - A deployment where repeated resolution happens to remain stable is merely
    consistent and is not repository-level affirmative evidence.
- reasoning: The natural source task already contains the semantic gap between
  preflight validation and the actual connected destination. There is no
  repository-backed true source state within the bounded history.

## candidate_I

- task identifier: none
- issue: none
- PR: none
- commit: none
- date: none
- files/functions: none
- exact invalidating transition: none; review stopped at Gate B.

## GATE_C

- status: `NOT_REACHED`
- affirmative evidence p*(I)=FALSE: not evaluated as I because p* was already
  false at the natural source task.
- contradictory evidence: not applicable
- reasoning: Advisory fix `ba949522...` adds connection-time protection and
  therefore moves the proposition toward true; it is not I.

## S_I_relationship

- same function/code path: not applicable
- commit ancestry: not applicable
- issue/PR relationship: issue #24179 identifies #20747 as the already
  incomplete earlier fix, not a true S followed by a later I.
- shared implementation mechanism: initial PR #16583 introduced
  `session.post`; #20747 placed a preflight validator before it without binding
  the validated destination to the connection.
- other provenance: frozen issue, PR, blame, and fix evidence agree on this
  chronology.

## unresolved_questions

No repository-backed interval was found where connected webhook destinations
were guaranteed to be those already validated. No C search was performed.

## new_evidence_retrieved

None beyond the frozen packet/raw/Git-history evidence.
