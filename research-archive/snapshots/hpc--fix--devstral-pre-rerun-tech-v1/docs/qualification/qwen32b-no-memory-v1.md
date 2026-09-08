# Qwen32B no-memory qualification v1

This treatment-blind suite freezes all seven tasks before any qualification model
result is observed. It contains no memory block and does not reuse calculator or
future security-treatment fixtures.

The canonical inputs are:

- qualified stack: `qualification/qwen32b-v1/freeze-manifest.json`
- suite and scoring rule: `qualification/qwen32b-v1/suite-manifest.json`
- considered, accepted, and rejected candidates:
  `qualification/qwen32b-v1/candidate-log.json`
- task manifests: `qualification/qwen32b-v1/tasks/`
- immutable external oracles: `oracles/qualification/v1/`
- hidden validation-only reference patches:
  `qualification/qwen32b-v1/reference-patches/`

The five primary tasks, in frozen order, are:

1. `qnm-p01-interval-merge` — localized logic correction
2. `qnm-p02-shipment-summary` — repository navigation
3. `qnm-p03-page-window` — input validation and boundary handling
4. `qnm-p04-record-parser` — parsing and API behavior
5. `qnm-p05-event-replay` — cross-function state/data flow

The two reserves are `qnm-r01-dependency-order` and
`qnm-r02-ledger-transfer`.

Every task is a small dependency-free vendored Python repository. Validation requires
an unpatched hidden-oracle failure, a reference-patch hidden-oracle pass, immutable
oracle isolation, protected visible tests, deterministic preparation, and exact
source/oracle/patch hashes. The reference patches are never copied into the agent
repository or prompt.

Repository competence is independent of the completion sentinel. Four or more of
the five primaries is suite PASS; exactly three is BORDERLINE and triggers both
preselected reserves, requiring five of seven overall; two or fewer is FAIL. A
technical infrastructure failure may receive one cause-corrected rerun, while a
model-level failure may not be rerun for a better outcome.

The annotated tag `qwen32b-qualification-v1` points to the exact job-25887 harness
commit `ba039a0eaddc358d6b7174260c3b3c36169c44c0`. Qualification scaffolding lives in a
later commit and must not move that tag.
