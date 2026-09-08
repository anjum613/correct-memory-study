# Benchmark selection v0.1

This namespace defines the auditable selection framework for **Correct Memory,
Vulnerable Patch: Causal Security and Decisive-Precondition Preservation in
Coding Agents**. It contains no selected repositories, treatment outcomes, or
model runs.

The fixed order is:

1. reproducible candidate discovery;
2. deterministic feasibility filters;
3. human trust-condition screening;
4. controlled triplet construction;
5. executable functionality/security validation;
6. independent outcome-blind review;
7. stratified selection;
8. frozen benchmark;
9. only then, memory-treatment runs.

Records may be appended to `candidate-ledger.jsonl` only under
`selection-protocol-v0.1.md` and `candidate.schema.json`. One line is one
candidate record; candidate IDs are unique. Within each record,
`status_history` is append-only and sequence numbered. A raw `DISCOVERED`
record is not a screened, eligible, selected, reserved, or frozen benchmark
item.

Validate the ledger with existing project Python only:

```bash
python scripts/validate-candidate-ledger.py
```

The ledger validator checks structural and outcome-blindness invariants. The
separate discovery command captures public forge metadata and materializes raw
records; it never clones repositories, executes reference patches, or decides
whether a human mechanism argument is scientifically persuasive.

## File roles

- `selection-protocol-v0.1.md`: authoritative process and decision rules.
- `candidate.schema.json`: machine-readable candidate record contract.
- `exclusion-codes.yaml`: controlled hard-exclusion vocabulary.
- `scoring-rubric.yaml`: post-gate 0–3 scoring and deterministic tie-break.
- `mechanism-card-template.yaml`: construction record for one proposed triplet.
- `reviewer-form.md`: independent outcome-blind review form.
- `replacement-policy.md`: objective reserve and replacement rules.
- `candidate-ledger.jsonl`: versioned candidate records; currently eight raw
  `DISCOVERED` records from `github-python-2024-medium-001`, now linked to
  static Stage-1 evidence but with no mechanism assignment, scoring, or
  selection.
- `discovery/v0.1/`: frozen query, source-list contract, and immutable captures.
- `discovery/prospective-v0.1/`: committed but unexecuted specifications for
  three additional discovery strata and cross-source identity handling.
- `stage1/v0.1/`: static objective-fact inspection protocol, schema, and frozen
  batch specification. It does not install or execute candidate code.
- `../scripts/discover_candidates.py`: capture, materialize, and verify command.
- `../scripts/stage1_screen_candidates.py`: screen, attach, and verify Stage-1
  evidence after its method commit is clean.

The benchmark is not frozen merely because the ledger validates. Freeze also
requires the approvals, executable evidence, hashes, and absence-of-treatment-
results certification specified in the protocol.

## Current discovery status

The first source snapshot is
`discovery/v0.1/snapshots/github-python-2024-medium-001/`. Its query was
committed before capture. All eight API results were imported in source order.
The snapshot and ledger certify `treatment_results_consulted: false`. Static
Stage-1 screening resolved all eight immutable commits, passed six licence
signals, and left two licence signals plus every setup, baseline-test,
task-size, and service-independence gate at `NEEDS_REVIEW`. Mechanism gates are
`NOT_ASSESSED`. All eight remain `DISCOVERED`; none is accepted, excluded,
eligible, selected, reserved, or frozen.
