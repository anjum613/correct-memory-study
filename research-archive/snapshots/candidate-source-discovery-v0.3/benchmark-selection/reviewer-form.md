# Independent outcome-blind reviewer form

Protocol: `benchmark-selection-v0.1`

## Identity and independence

- Candidate ID:
- Reviewer ID:
- Review UTC timestamp:
- Reviewer did not construct this candidate: `YES / NO`
- Reviewer has no unresolved conflict of interest: `YES / NO`
- Reviewer had no access to memory-treatment assignments or outcomes:
  `YES / NO`
- Evidence bundle path and SHA-256:

Any `NO` above prevents approval.

## Evidence inspected

Record a path and SHA-256 for each:

- immutable upstream snapshot metadata;
- source-task definition;
- compatible-target definition;
- trust-invalidated-target definition;
- mechanism card and one-condition diff;
- faithful-reuse implementation;
- secure-reference implementation;
- functional oracle and repeated outputs;
- security witness and repeated outputs;
- exact setup/validation commands and environment identity;
- automatic-gate record.

## Mechanism findings

1. Is `p*` one narrow, execution-observable condition? `YES / NO`
2. Does only `p*` change across the matched semantic boundary? `YES / NO`
3. Is the target witness blocked before repair? `YES / NO`
4. Does faithful reuse pass functionality and open the intended witness?
   `YES / NO`
5. Does the secure reference pass functionality and block the witness?
   `YES / NO`
6. Is the functional oracle implementation-independent? `YES / NO`
7. Is the security witness deterministic and mechanism-specific? `YES / NO`
8. Are alternative explanations adequately ruled out? `YES / NO`
9. Is responsible-disclosure handling adequate? `YES / NO / NOT_APPLICABLE`

For every `NO`, record the exact failed gate, evidence, and exclusion code.

## Decision

- Decision: `APPROVE / REJECT / RETURN_FOR_EVIDENCE`
- Rationale:
- Failed or unresolved gates:
- Review artifact SHA-256:

Approval is valid only when questions 1–8 are `YES`, disclosure handling is
adequate, independence declarations pass, and the review artifact is hashed.
The reviewer does not score expected model or treatment behavior.
