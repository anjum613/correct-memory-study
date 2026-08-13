# Protocol changes

This is an append-only amendment register. Historical plans remain visible;
new entries may refine future execution but must not rewrite prior records.

## PC-001 — provisional qualified-model substitution

- Effective date: `2026-08-12`
- Applies to: prospective treatment-runner freeze
- Status: `PROVISIONAL_PENDING_RUNTIME_INSPECTION`
- Original planned system: `Qwen2.5-Coder-32B`
- Provisional qualified system: `Qwen/Qwen3.6-27B`
- Immutable revision: `6a9e13bd6fc8f0983b9b99948120bc37f49c13e9`
- Qualification result: repository competence `4/5`, decision `PASS`
- Qualification evidence: `qualification/qwen36-v1/qualification-result.json`

Rationale: the original model remains part of the historical proposal. The
currently qualified candidate is recorded as a prospective substitution, not
silently rewritten into that history.

The final treatment-runner freeze remains subject to completed inspection of
Slurm job `26336`. Job `26336` is the frozen synthetic four-condition GPU
runtime validation, not a treatment run and not a calculator run. This entry
does not authorize inspection of partial artifacts, modification of the live
worktree, or treatment execution.

Any transition from provisional to frozen must record the inspected completed
job identity, its technical-validity decision, the final runner configuration,
all relevant hashes, and a certification that benchmark selection did not use
memory-treatment outcomes.

## PC-002 — raw discovery records precede mechanism assignment

- Effective timestamp: `2026-08-12T14:35:12Z`
- Applies to: candidate discovery and mechanism screening
- Status: `APPLIED_PROSPECTIVELY_BEFORE_DISCOVERY`
- Candidate discovery begun: `NO`
- Candidate screening or construction begun: `NO`
- Benchmark selection or treatment begun: `NO`
- Treatment assignments or outcomes viewed: `NO`

The original v0.1 schema required a trust family and mechanism key even in the
initial `DISCOVERED` state. That would force an unsupported scientific judgment
during mechanical repository discovery. A raw discovered repository may now
record both fields as null. Both fields remain mandatory from
`MECHANISM_REVIEW_PASSED` onward. No state transition, gate, stratum, score,
cap, replacement rule, treatment definition, or outcome rule changes.

The first discovery query and pipeline are committed before any live source
response is captured. This entry therefore changes no observed candidate,
screening decision, selected set, treatment assignment, or result.

## PC-003 — conservative Stage-1 uncertainty status

- Effective timestamp: `2026-08-12T17:21:24Z`
- Applies to: automatic feasibility screening
- Status: `APPLIED_PROSPECTIVELY_BEFORE_STAGE1_SCREENING`
- Existing generic discovery completed: `YES`, eight identities known
- Stage-1 screening begun: `NO`
- Mechanism review or triplet construction begun: `NO`
- Additional source specifications executed: `NO`
- Benchmark selection or treatment begun: `NO`
- Treatment assignments or outcomes viewed: `NO`

The gate status `NEEDS_REVIEW` is added to distinguish ambiguity from both
`FAIL` and `NOT_ASSESSED`. It does not change a hard gate's meaning. Static
repository inspection cannot by itself prove reproducible installation,
deterministic tests, manageable task size, or independence from credentials
and uncontrolled services. Those facts therefore remain `NEEDS_REVIEW` until
the corresponding controlled check or human review is recorded.

Only an exact hard-gate failure may move a candidate to `EXCLUDED`. Only six
automatic `PASS` decisions may move it to `AUTOMATIC_GATES_PASSED`. This
amendment does not assign a trust family, define `p*`, construct references,
score, rank, select, or use treatment information.

## PC-004 — raw source records and content-addressed candidate identity

- Effective timestamp: `2026-08-13T02:07:39Z`
- Applies to: prospective execution of the three additional discovery sources
- Status: `FROZEN_NOT_EXECUTED`
- Failed v0.1 audit commit: `4162f99d6b45615d8bad05631b5dd46c516d34f0`
- Additional-source identity fetch performed: `NO`
- Existing generic discovery identities changed: `NO`
- Benchmark selection or treatment begun: `NO`
- Experiment artifacts accessed: `NO`
- Treatment assignments or outcomes viewed: `NO`

The failed v0.1 source specifications remain immutable. Their finite
source-range IDs, missing raw-record layer, and incomplete normalization rules
are superseded prospectively by v0.2 only for later additional-source
execution.

Every later source object must receive an append-only source record, whether
it is `MATERIALIZED` or `SOURCE_REJECTED`. A candidate-ledger record may be
created only when positive immutable repository, pre-repair snapshot, repair,
and artifact identity is present. Source-record IDs are content-addressed
within an immutable source revision. Canonical candidate IDs are
content-addressed from GitHub repository numeric ID plus exact repair commit
SHA and are never renumbered when another source is added.

Automatic cross-source collapse requires positive immutable equality. Missing
values never act as wildcards; weaker overlap is preserved as
`POSSIBLE_DUPLICATE`. Source priority controls provenance presentation only.
It cannot affect scientific ranking, eligibility, replacement, or selection.

The amendment also freezes a non-executable BugsInPy metadata grammar, exact
advisory predicates and repair-anchor rules, and merged-PR materialization for
the eight public GitHub searches. It does not assess semantic bug suitability,
assign a trust family, define `p*`, construct a triplet, score a candidate, or
authorize source execution.
