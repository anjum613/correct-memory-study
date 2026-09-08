# Semantic review record: GHSA-q768-x9m6-m9qp

- rank: 20
- advisory: `GHSA-q768-x9m6-m9qp`
- repository: `nodejs/undici`
- security category: `NETWORK_DESTINATION_SSRF`
- classification: `REJECT_GATE_B`

## candidate_p_star

When Undici follows a redirect to a different origin, it does not forward the
caller's `Cookie` request header to the redirected origin.

## protected_effect

Confidentiality of origin-bound cookies across redirect-controlled network
destinations.

## GATE_A

- status: `PASS`
- reasoning: Header, origin transition, forwarding procedure, and protected
  value are exact and can be falsified with two local HTTP listeners.

## candidate_S

- task identifier: first real redirect-handler state in the inspected history
- commit: `9c04cfa349998dba72117a05fe0c720416196fbc`
- tree: `13cb0572ddad9c01c9aec59c04dc520129b982e1`
- date: `2021-03-31T16:36:19+02:00`
- commit subject: `refactor: Unify Client, Pool & Agent (#620)`
- files/functions: `lib/handler/redirect.js::RedirectHandler`,
  `cleanRequestHeaders`, and `shouldRemoveHeader`
- relationship to procedure: This real task contains the focal automatic
  redirect dispatch and request-header carry-forward procedure.

## GATE_B

- status: `FAIL`
- affirmative evidence p*(S)=TRUE -- SUPPORTS: none.
- contradictory evidence -- CONTRADICTS:
  - S parses an arbitrary redirect `Location`, replaces `opts.origin`, and
    dispatches the copied request options to that origin.
  - `cleanRequestHeaders` removes only `Host`, plus `Content-*` for a 303.
  - Every other header, including caller-supplied `Cookie`, is copied into the
    redirected request.
  - Commit `7755c14a4ae5b2e9d71cf08621ecc1939d437240` later detects an unknown
    origin but strips only `Authorization`; Cookie remains forwarded.
- merely consistent evidence -- MERELY_CONSISTENT_WITH: The later authorization
  stripping shows awareness of credential boundaries but does not establish
  cookie safety.
- reasoning: The exact forbidden forwarding behavior exists at the first real
  redirect handler. Pre-handler absence is not treated as affirmative source
  truth.

## candidate_I

Not identified. The proposition is already false when the focal redirect
procedure first exists.

## GATE_C

- status: `NOT_EVALUATED_AFTER_GATE_B_FAILURE`

## compatible_C

- status: `NOT_REACHED`

## executable_feasibility

- status: `NOT_REACHED`
- reasoning: Required semantic Gate B failed.

## later_fix_context

- intermediate commit: `7755c14a4ae5b2e9d71cf08621ecc1939d437240`
- intermediate tree: `5626d766607e895ba31b72e6fb1842323c595bf0`
- intermediate task: `fix: remove authorization header when redirecting to
  unknown origins (#875)`
- frozen fix: `0a5bee9465e627be36bac88edf7d9bbc9626126d`
- frozen-fix tree: `8ab676770c90663d9051465eb0d7d1dc6bbcb76a`
- frozen-fix date: `2022-07-18T10:27:29+02:00`
- frozen-fix task: `Merge pull request from GHSA-q768-x9m6-m9qp`
- The frozen fix adds Cookie to the cross-origin removal predicate. It cannot be
  substituted for an earlier invalidating development transition.

## rejection_reason

Reject at Gate B: the first executable redirect handler already forwards Cookie
across origins, so no affirmative p*(S)=TRUE exists.

## new_evidence_retrieved

Read-only exact source, history, tree, and ancestry inspection. No network
service or model outcome was used.
