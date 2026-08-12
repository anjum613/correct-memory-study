# Repository-selection protocol v0.1

Protocol identifier: `benchmark-selection-v0.1`

## 1. Scope and non-negotiable order

This protocol selects controlled security triplets derived from real
open-source repositories. Selection is outcome-blind. No treatment result,
expected treatment effect, apparent memory following, memory completeness, or
support for the hypothesis may accept, reject, score, rank, replace, or retain
a candidate.

The order is discovery → automatic gates → mechanism review → triplet
construction → executable validation → independent review → stratified
selection → freeze → treatment. A later stage cannot retrospectively alter an
earlier decision except through the amendment and replacement rules below.

## 2. Candidate unit and sources

One candidate is one upstream repository at one immutable commit plus one
proposed mechanism. Discovery records must contain:

- the versioned query or source-list identifier;
- forge, canonical repository URL, upstream owner and repository name;
- discovery timestamp and discoverer identity;
- licence expression and evidence;
- full commit SHA, commit timestamp, tree SHA-256, metadata SHA-256, and the
  retrieval/export method needed to reproduce the snapshot;
- source-list position before any screening decision.

Permitted candidate sources are versioned forge/API query exports, archived
curated lists, and prior source lists whose exact bytes and query parameters
are preserved. Convenience recommendations may propose a source list but are
not selection evidence until converted into a reproducible snapshot. This task
does not execute discovery or clone candidates.

## 3. Controlled triplet design

The base is a real open-source repository. Minimal controlled unpublished
variants define:

- a source task in which the repair procedure is valid;
- a compatible target in which its decisive precondition remains true;
- a trust-invalidated target in which exactly one narrow condition `p*`
  changes;
- a faithful-reuse implementation that applies the source-valid procedure;
- a secure-reference implementation that checks or adapts to `p*`;
- one deterministic, implementation-independent functional oracle; and
- one deterministic security witness.

Before repair, the target must pass the functional baseline and block the
security witness. Faithful reuse must pass functionality and open only the
intended witness. The secure reference must pass the same functionality and
keep that witness blocked. All other task-relevant semantics are matched.

Allowed trust-family strata are:

1. `TRUSTED_DATA_BECOMES_ATTACKER_INFLUENCED`;
2. `INTERNAL_FUNCTIONALITY_BECOMES_EXTERNALLY_REACHABLE`;
3. `AUTHORIZATION_ROLE_TENANT_OR_RESOURCE_SCOPE_CHANGES`;
4. `VALIDATION_RESPONSIBILITY_MOVES_DISAPPEARS_OR_IS_BYPASSED`.

The mechanism key is the normalized tuple `(trust_family, affected_boundary,
decisive_condition_kind)`. It is frozen before scoring.

## 4. States and append-only history

Each unique candidate record has `current_state` and an append-only,
sequence-numbered `status_history`. The first state is `DISCOVERED`; the last
history state equals `current_state`.

The forward path is:

`DISCOVERED` → `AUTOMATIC_GATES_PASSED` → `MECHANISM_REVIEW_PASSED` →
`TRIPLET_VALIDATED` → `INDEPENDENT_REVIEW_APPROVED` → `ELIGIBLE` →
(`SELECTED` or `RESERVE`) → `FROZEN`.

`RESERVE` may move to `SELECTED` only through the replacement policy and then
to `FROZEN`. Any non-frozen state may move to `EXCLUDED`. `EXCLUDED` and
`FROZEN` are terminal. Every transition records UTC time, actor, protocol
version, rationale, and evidence hashes. History entries are never removed,
reordered, or rewritten.

## 5. Hard gates

Every gate is recorded as `PASS`, `FAIL`, or `NOT_ASSESSED`. A candidate cannot
be independently approved, eligible, selected, reserved, or frozen unless all
hard gates pass.

### Automatic feasibility gates

1. `usable_licence`: redistribution and controlled research modification are
   permitted and documented.
2. `immutable_commit`: an immutable full commit and snapshot metadata exist.
3. `reproducible_setup`: setup is repeatable in a controlled environment.
4. `deterministic_baseline_tests`: baseline tests produce stable results.
5. `manageable_task_size`: construction and execution fit the frozen resource
   and context budgets without deleting essential semantics.
6. `no_proprietary_credentials_or_uncontrolled_service`: no private credential,
   paid/proprietary dependency, or uncontrolled live service is required.

### Mechanism and validation gates

7. `narrow_observable_p_star`: `p*` is singular, explicit, and execution-
   observable.
8. `one_condition_isolation`: source/compatible/invalidated variants differ in
   the decisive trust condition, not a bundle of semantic changes.
9. `target_not_already_vulnerable`: the intended witness is blocked in the
   invalidated target before repair.
10. `faithful_reuse_functional_and_witness_open`: faithful reuse passes
    functionality and opens the intended witness.
11. `secure_reference_functional_and_witness_blocked`: the secure reference
    passes functionality and blocks the witness.
12. `implementation_independent_functional_oracle`: functionality does not
    encode either reference implementation.
13. `deterministic_security_witness`: repeated controlled executions agree and
    isolate the intended security property.
14. `independent_approval`: an eligible independent reviewer approves the
    complete pre-treatment evidence.

A failed hard gate produces `EXCLUDED`, an exclusion code, stage, explanation,
and evidence references. Missing evidence is not a pass.

## 6. Human mechanism review

Before implementation, a mechanism reviewer completes a mechanism card and
confirms the trust family, `p*`, attacker influence or reachability, expected
pre-repair witness block, minimal variant delta, and why faithful reuse is
functionally correct but trust-incompatible. A reviewer cannot infer a gate
from the hoped-for treatment response.

After executable validation, at least one independent reviewer who did not
construct the candidate must review the source and three variants, both
references, oracle, witness, exact commands, repeatability evidence, and
mechanism card. The reviewer must certify no access to treatment outcomes,
declare conflicts, and record `APPROVE`, `REJECT`, or `RETURN_FOR_EVIDENCE`.
Approval requires no unresolved conflict and a hashed review artifact.

## 7. Post-gate scoring and stratified selection

Only `ELIGIBLE` candidates are scored. Each dimension in
`scoring-rubric.yaml` receives an integer 0–3 from pre-treatment evidence.
Zero is permissible after all hard gates pass; it means low comparative merit,
not gate failure. Scores never include expected treatment effect, expected
memory following, memory completeness, or apparent support for the hypothesis.

Selection proceeds by trust-family strata with a deterministic round-robin
over strata that have eligible candidates. Within a stratum candidates sort by
descending total score, then ascending seeded tie-break digest. The seed is
frozen in the rubric before candidate scoring.

Caps are mandatory:

- at most one selected triplet per upstream repository in one benchmark
  version;
- at most two selected triplets per normalized mechanism key.

If a cap removes a candidate from the selected positions, it remains eligible
for the reserve list only if adding it later could satisfy all caps.

## 8. Reserve list and replacement

Reserves are ordered during the same outcome-blind selection pass using the
same stratum, score, tie-break, and cap rules. Replacement uses
`replacement-policy.md`. No run outcome can trigger or choose a replacement.
Once any treatment outcome for the benchmark is accessible, no candidate may
be replaced; technical invalidity is handled under the frozen run protocol and
all evidence is preserved.

## 9. Benchmark freeze

Freeze requires:

- protocol version and all amendment IDs;
- immutable upstream snapshot metadata;
- source, compatible, and invalidated definitions and hashes;
- `p*`, trust family, and mechanism key;
- faithful-reuse and secure-reference artifacts and hashes;
- deterministic functional-oracle and security-witness artifacts and hashes;
- exact setup and validation commands, dependency/environment identities, and
  repeated execution records;
- complete hard-gate, scoring, exclusion, independent-review, selected, and
  reserve records;
- selection seed, tie-break algorithm, caps, and final ordering;
- a self-excluding manifest over all freeze artifacts; and
- a signed/attributed certification that treatment results were absent and
  inaccessible at freeze.

Every file referenced by a frozen record has a lowercase SHA-256. Missing
hashes invalidate the freeze. Freeze artifacts are immutable; corrections use
a new version and amendment without deleting the prior version.

## 10. Amendments

Protocol amendments are append-only, versioned, dated, justified, and hashed.
They state whether candidate discovery, screening, construction, selection, or
treatment outcomes had begun or been viewed. Before treatment outcomes, an
amendment may prospectively change procedure and must rerun all affected gates
for every candidate. After any treatment outcome is viewed, amendments cannot
change candidate membership, treatment definitions, witnesses, scores, strata,
caps, tie-breaking, reserves, or replacement order for that benchmark version.

## 11. Responsible disclosure

Candidate construction uses unpublished controlled variants. If work reveals
a plausible undisclosed vulnerability in the upstream repository, public
technical detail is embargoed, access is restricted, and maintainers are
contacted through an appropriate private channel. Disclosure timing and scope
follow maintainer guidance and institutional policy. The discovery is
preserved as evidence but cannot be used as a favourable selection signal.
Exclusion or replacement, if objectively required, follows the pre-treatment
rules and is recorded without exposing exploit details.

## 12. External validity

The selected benchmark is purposive and stratified. It supports causal claims
for the frozen within-target contrasts under this protocol, not prevalence or
population-wide performance claims across repositories, agents, models,
languages, security mechanisms, or real-world vulnerabilities.
