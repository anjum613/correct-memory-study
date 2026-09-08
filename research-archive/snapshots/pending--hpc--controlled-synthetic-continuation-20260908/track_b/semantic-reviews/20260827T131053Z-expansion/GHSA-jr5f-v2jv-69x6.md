# Semantic review record: GHSA-jr5f-v2jv-69x6

- rank: 17
- advisory: `GHSA-jr5f-v2jv-69x6`
- repository: `axios/axios`
- security category: `NETWORK_DESTINATION_SSRF`
- classification: `REJECT_GATE_B`
- duplicate-repository note: This is a second frozen Axios advisory. The
  duplicate repository was not used as the rejection reason, and the existing
  frozen Axios family was not inspected or modified.

## candidate_p_star

When an Axios instance has a configured `baseURL` and
`allowAbsoluteUrls: false`, an absolute request URL cannot override that base
and select a different network destination in any request adapter.

## protected_effect

Configured network-destination confinement and prevention of SSRF or credential
leakage to a caller-selected absolute URL.

## GATE_A

- status: `PASS`
- reasoning: Configuration, input class, adapter operation, and destination
  effect are exact and locally falsifiable.

## candidate_S

- task identifier: `Add config for ignoring absolute URLs`
- PRs: [#5902](https://github.com/axios/axios/pull/5902),
  [#6192](https://github.com/axios/axios/pull/6192)
- commit: `32c7bcc0f233285ba27dec73a4b1e81fb7a219b3`
- tree: `c245231da46a0af66ea7b457034ce293054b14c9`
- date: `2025-02-12T04:09:24-05:00`
- files/functions: `lib/core/Axios.js`, `lib/core/buildFullPath.js`, README and
  option/core tests
- relationship to procedure: This is the first task that introduces and
  advertises the exact `allowAbsoluteUrls: false` contract.

## GATE_B

- status: `FAIL`
- affirmative evidence p*(S)=TRUE -- SUPPORTS: none for actual adapter dispatch.
- contradictory evidence -- CONTRADICTS:
  - S passes `allowAbsoluteUrls` to `Axios.getUri` and the core helper, but the
    Node HTTP adapter still calls `buildFullPath(config.baseURL, config.url)`
    without passing the flag.
  - Consequently the adapter retains the old absolute-URL override behavior at
    the contract's introduction.
  - S's browser options test also expects an absolute other-origin request URL,
    demonstrating that it does not prove destination confinement.
- merely consistent evidence -- MERELY_CONSISTENT_WITH: README claims and core
  helper tests are consistent with the intended feature but cannot establish
  adapter-level truth.
- reasoning: The source task's advertised invariant is affirmatively false in
  the focal executable path. It cannot serve as p*(S)=TRUE.

## candidate_I

Not identified. The invariant fails at its first applicable source task, so the
review stops at Gate B. Later repair commits cannot be substituted for a real
S-to-I development transition.

## GATE_C

- status: `NOT_EVALUATED_AFTER_GATE_B_FAILURE`

## compatible_C

- status: `NOT_REACHED`

## executable_feasibility

- status: `NOT_REACHED`
- reasoning: Required semantic Gate B failed.

## later_fix_context

- main-line repair: `fb8eec214ce7744b5ca787f2c3b8339b2f54b00f`, tree
  `b489cfc208136431b1d7726c77e5753f0fe68f28`, `fix(http-adapter): add
  allowAbsoluteUrls to path building (#6810)`.
- exact ranked backport fix: `02c3c69ced0f8fd86407c23203835892313d7fde`,
  tree `70ff352fd69f4ecee7a1ef92543a9b58041a90cd`, `fix: backport
  allowAbsoluteUrls vuln fix to v0.x (#6829)`.
- These are fixes, not affirmative source truth or an independent invalidating
  development task.

## rejection_reason

Reject at Gate B: no affirmative p*(S)=TRUE; the contract is incomplete and
false from introduction.

## new_evidence_retrieved

Read-only inspection of exact source, main-line repair, and seeded backport
commits and trees. No prior Axios family outcome was used.
