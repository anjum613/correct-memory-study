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
