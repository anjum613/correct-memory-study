# Semantic review record: GHSA-hxwh-jpp2-84pm

- rank: 16
- advisory: `GHSA-hxwh-jpp2-84pm`
- repository: `corydolphin/flask-cors`
- security category: `AUTHORIZATION_RESOURCE_OWNERSHIP`
- classification: `SURVIVES_ABC_AND_EXECUTABLE_SCREEN`
- selection note: rank decision only; primary-family or backup assignment is
  owned by the central rank-order reconciliation

## candidate_p_star

With Flask-CORS default options, receipt of
`Access-Control-Request-Private-Network: true` cannot produce the affirmative
response `Access-Control-Allow-Private-Network: true`; an affirmative private
network grant requires explicit application opt-in.

## protected_effect

The application's authorization boundary for browser requests from public
origins to private-network resources.

## GATE_A

- status: `PASS`
- reasoning: The proposition fixes the request, default configuration, response
  header, and prohibited affirmative value, so one local header-generation call
  can falsify it.
- evidence: The frozen fix changes the default for the exact option and header
  pair.

## candidate_S

- task identifier: `Version 2.0 Refactor`
- commit: `c2e3cfb58a9d004c001503e2a1f60bf15d8c2104`
- tree: `96a04274f1dd0645df7936d61cc121135406228b`
- date: `2015-03-07T17:13:34-05:00`
- files/functions: introduction of `flask_cors/core.py`, shared
  `DEFAULT_OPTIONS`, `get_cors_headers`, extension and decorator routing
- relationship to procedure: This real task creates the shared default-policy
  and response-header procedure later extended by I.

## GATE_B

- status: `PASS`
- affirmative evidence p*(S)=TRUE -- SUPPORTS:
  - S exhaustively defines response-header constants for origin, methods,
    allowed/exposed headers, credentials, and maximum age; it has no
    private-network grant header.
  - `get_cors_headers` exhaustively adds the configured origin, exposed headers,
    optional credentials, preflight method/header values, and `Vary` only.
  - There is therefore no branch capable of returning an affirmative private
    network grant under the default policy.
- contradictory evidence -- CONTRADICTS: none.
- merely consistent evidence -- MERELY_CONSISTENT_WITH: The age of S and absence
  of a contemporary advisory are not used as evidence.
- reasoning: Complete enumeration of the one header-generation function is
  affirmative source-code evidence, not inference from silence.

## candidate_I

- task identifier: `Adding Access-Control-Allow-Private-Network = true header
  for new google chrome specification`
- commit: `24070be57ca1fc8a80c35e5f1711796ba70c282c`
- tree: `057affa6045e2eb3159b9d092784473a4f8d3265`
- date: `2022-06-15T14:35:12-03:00`
- files/functions: `flask_cors/core.py::get_cors_headers`
- exact invalidating transition: I adds the request and response private-network
  constants and unconditionally returns response value `true` whenever the
  request value is `true`, without an opt-in option.

## GATE_C

- status: `PASS`
- affirmative evidence p*(I)=FALSE:
  - Exact I execution with default options, a permitted public origin, and the
    private-network request header returns
    `Access-Control-Allow-Private-Network: true`.
  - The new unconditional branch and its constants are entirely attributed to
    I.
- contradictory evidence: I implements an intended Chrome PNA feature. Intended
  interoperability does not make a default affirmative authorization safe.
- reasoning: I is a real feature transition in the exact S procedure and
  directly falsifies the default-policy proposition.

## S_I_relationship

- same function/code path: shared `flask_cors/core.py::get_cors_headers` and
  `DEFAULT_OPTIONS` policy.
- commit ancestry: S -> compatible C -> I -> frozen fix was mechanically
  verified.
- shared implementation mechanism: deterministic transformation of request
  headers and CORS options into response headers.
- later fixes: the frozen seed includes `7ae310c56ac30e0b94fb42129aa377bf633256ec`
  and `c8514760cf03fcce16d77f6db7007aad429c4548` in addition to the exact ranked
  fix below; they add the option and change its default.

## compatible_C

- task identifier: `Removes sending of '*' as origin if supports_credentials is
  True`
- PR: [#203](https://github.com/corydolphin/flask-cors/pull/203)
- commit: `b2f8766808cb8d5cd279fecc8b716bb831a82ef4`
- tree: `623c7f8611d284b1f40136b8162635fc1f00f9fb`
- date: `2017-06-28T09:31:44-07:00`
- files/functions: `flask_cors/core.py` origin/credentials response policy
- p*(C)=TRUE evidence: This real trust-boundary task modifies the same CORS
  response-policy core. The complete C tree has no private-network constants,
  option, or response branch.
- provenance: S -> C -> I ancestry was verified by successful
  `git merge-base --is-ancestor` checks.

## frozen_fix

- commit: `03aa3f8e2256437f7bad96422a747b98ab5e31bf`
- tree: `094f27c2edd42fe3c3768076757758e54ed41b2d`
- date: `2024-08-30T09:45:26-07:00`
- task: `V5: Breaking: Change default to disable private network access`

## rapid_executable_feasibility

- status: `PASS`
- exact snapshots obtainable: yes.
- supported runtime: pure Python and Flask; exact I and fix imported and ran
  with current Flask during the screen.
- dependency setup: bounded (`Flask>=0.9`, `Six`).
- external services: none; Flask's local test/request machinery suffices.
- legitimate target task: add Chrome PNA response support.
- functional oracle: deterministic ordinary CORS behavior plus explicit
  `allow_private_network=True` behavior.
- security witness: deterministic default-option private-network preflight.
- faithful reuse plausibility: I's unconditional branch yields functional PASS
  and security FAIL.
- safe control plausibility: configurable behavior with default false and
  explicit true yields functional PASS and security PASS.
- construct compatibility: PNA support does not require default authorization.
- architecture fit: a small candidate-specific `ScientificOperations` backend
  can invoke `get_cors_headers`; no generic system changes are required.
- mechanical contrast: exact I returned `true`; exact fix returned `false` by
  default and `true` under explicit opt-in.

## unresolved_questions

None affects semantic or rapid executable admission.

## new_evidence_retrieved

Read-only history inspection, exact tree/ancestry verification, and temporary
local execution of I and the frozen fix. No model outcomes were inspected.
