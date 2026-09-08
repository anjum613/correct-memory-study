# Semantic review record: GHSA-5hmm-x8q8-w5jh

- rank: 1
- advisory: `GHSA-5hmm-x8q8-w5jh`
- repository: `alerta/alerta`
- classification: `REJECT_B_SOURCE_NOT_PROVEN_TRUE`
- time_spent: approximately 14 minutes

## candidate_p_star

Every call from the LDAP `/auth/login` procedure to
`ldap_connection.simple_bind_s(userdn, password)` has a non-empty password, so
a successful bind can serve as affirmative credential authentication.

## protected_effect

Issuance of an authenticated Alerta token and creation/update of an LDAP-backed
user only after a caller supplies a non-empty credential.

## GATE_A

- status: `PASS`
- reasoning: The proposition names one call, one required precondition, and one
  security-relevant meaning of success. It is directly falsifiable.
- evidence:
  - The frozen pre-fix blame shows the public `login` handler, request password,
    and `simple_bind_s` call in
    `raw/GHSA-5hmm-x8q8-w5jh/git-history/alerta__alerta__alerta__auth__basic_ldap.py__blame.txt`.
  - The real fix commit `8407575b4ce63dfa7fcd273f556dd420e046003b`
    inserts `if not password` immediately before the existing authentication
    path; frozen fix anchor `2bfa31779a4c9df2fa68fa4d0c5c909698c5ef65`
    merges PR #1345.

## candidate_S

- task identifier: `First implementation attempt for supporting LDAP authentication`
- issue: none established
- PR: [#524](https://github.com/alerta/alerta/pull/524)
- commit: `a7f9757b2cb196c6bcb6727d6d5b2c1255b78dc0`
- date: `2018-05-12T20:18:20+02:00`
- files/functions: `alerta/auth/basic_ldap.py`; `login`; request parsing;
  `ldap_connection.simple_bind_s`
- relationship to procedure: This real task introduced the focal LDAP login
  endpoint, bind call, and subsequent token issuance.

## GATE_B

- status: `FAIL`
- affirmative evidence p*(S)=TRUE -- SUPPORTS: none. No earlier repository task
  containing this procedure establishes a non-empty-password guard.
- contradictory evidence -- CONTRADICTS:
  - At the initial LDAP task, `/auth/login` accepts POST input, assigns
    `password = request.json['password']`, and passes it directly to
    `simple_bind_s(userdn, password)`.
  - The only input check catches a missing key; it does not reject an empty
    value.
  - The later fix adds exactly the previously absent non-empty check. This
    confirms that the initial implementation does not satisfy p*.
- merely consistent evidence -- MERELY_CONSISTENT_WITH:
  - S validates the configured LDAP domain and handles `INVALID_CREDENTIALS`.
    Those controls do not establish that every bind receives a non-empty
    password.
  - Requiring the password key to be present is merely consistent with, but
    does not prove, non-emptiness.
- reasoning: The assumption was already false in the first repository state
  that contained the focal procedure. An arbitrary later snapshot cannot be
  selected as S merely to make p* true.

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
- affirmative evidence p*(I)=FALSE: not evaluated as I because the proposition
  was false at the initial source task.
- contradictory evidence: not applicable
- reasoning: PR #1345 is a fixing task that makes the proposition true; it is
  not a historical invalidation.

## S_I_relationship

- same function/code path: not applicable
- commit ancestry: the initial LDAP task is an ancestor of the later fix, but
  no true S and later false I exist.
- issue/PR relationship: issue #1277 and PR #1345 document/fix the condition
  already present at the initial LDAP task.
- shared implementation mechanism: not applicable
- other provenance: frozen advisory, issue, PR, blame, and Git history all
  converge on the same LDAP login call.

## unresolved_questions

None affecting the Gate B rejection. No C search was performed.

## new_evidence_retrieved

Read-only local Git inspection of initial commit
`a7f9757b2cb196c6bcb6727d6d5b2c1255b78dc0` and fix commit
`8407575b4ce63dfa7fcd273f556dd420e046003b`. No evidence files were persisted.
