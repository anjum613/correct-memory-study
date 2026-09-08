# Controlled synthetic V3 executable-oracle release v1

Release ID: `controlled-synthetic-v3-executable-oracle-release-v1`.

This separately versioned release replaces the previously recorded nonbehavioral
placeholder inputs with executable, isolated synthetic source/target fixtures and
behavioral oracles. The previous releases and their commits remain unchanged. The
original placeholder remains explicitly marked
`NONEXECUTABLE_PLACEHOLDER / SUPERSEDED_BEFORE_CONSTRUCTION`, and its generated
project-owner attestations remain marked `INVALID — NO HUMAN REVIEW OCCURRED`.

The frozen scientific specifications, order, four-attempt cap, machine and human
admission rules, full-pool retention amendment, X02/X22 clarification, six V2
families, and prohibition on outcome-informed selection are not changed here.
X19 and X25 retain their original slots and evidence as zero-attempt
`PRE_CONSTRUCTION_SPECIFICATION_UNDERSPECIFIED` exclusions. The remaining 26
families are processed in their unchanged relative order; neither exclusion is
replaced.

## Executable state contract

For every in-scope family, hand-controlled local references establish:

| State | Existing/source behavior | Requested feature | Focal invariant |
|---|---|---|---|
| S | PASS | source-functional PASS | PASS under the source condition |
| B | PASS | FAIL | PASS |
| U = B + `feature.patch` | PASS | PASS | FAIL for the intended behavioral condition |
| R = U + `security.patch` | PASS | PASS | PASS |

All fixtures operate only on deterministic in-memory/local synthetic state. They
do not contact real systems or services, use real credentials, or contain
operational exploit tooling. The sealed checks observe prohibited local state
transitions or effects directly. Crashes, timeouts, import errors and malformed
implementations are harness/infrastructure errors, never focal-security evidence.

The generated constructor envelope is under `agent_inputs/`. It contains the
frozen task, executable source, unfinished target scaffold, and public behavioral
feature checks. It contains neither researcher sealed tests nor reference repairs.
Four direct repair APIs are deliberately removed from its runtime so the repair
cannot be selected by an obviously named helper. Researcher-only invariant tests
are under `researcher_tests/` and are injected only by the trusted validator.

## Machine gate and isolation

The candidate artifact is exactly a B tree containing one canonical service file,
one `feature.patch`, and one `security.patch`. Both patches apply sequentially and
must yield three distinct regular-file trees. Extra files, links, device/special
files, binary/NUL/oversized content, executable modes, path changes, test changes,
and malformed or nonapplying patches fail closed.

Each B/U/R state runs with a fixed validator deadline in a private user, mount and
network namespace. A chroot exposes only read-only system runtimes, a curated
validator/test runtime, the read-only candidate state, `/dev/null`, and a small
private tmpfs. The wider repository is not mounted. Candidate Python is also
syntax/import restricted; X02 uses the closed CSIR-X02/1 interpreter with exact
work/storage accounting. A controlled X20 reference bundle proves the complete
production validator accepts the required matrix, while negative bundles prove it
rejects unfinished B, feature-failing U, secure U, insecure R, and
feature-regressing R.

The production admission ledger is pristine and immutable until a post-freeze
launcher supplies the committed release identity. A disposable-ledger model proves
frozen order, the four-attempt cap, first-machine-valid retention, and the fixed
600-second constructor deadline. No constructor call is made by any preflight.

## Scope of automation

The validator automates only executable feature/security, tree/patch, resource,
deadline, and canonical-integrity gates. Plausible direct procedural transfer,
single-mismatch cleanliness, target-answer leakage, complete semantic
applicability, and cross-family distinctness remain mandatory independent human
review criteria. No human-review file is created by this release.

`coverage_audit_results.json` maps every unchanged three-part target obligation to
the executed boundary, maximum-size, alternate-mode, failure, and interleaving
scenario classes relevant to that family. `reference_matrix_results.json` records
the trusted S/B/U/R results. `candidate_oracle_results.json` independently checks
the generated public/sealed runtime, and `validator_isolation_results.json` records
the exact isolated intended-U results.

`release_manifest.json` binds every release and validator test file plus the
unchanged upstream scientific/provenance files. Run `integrity.verify_release()`
from Python or the release-specific pytest files listed in that manifest. The
release commit and manifest SHA-256 are recorded afterward in
`commit_receipt.json`, avoiding a self-referential commit/hash claim.

At the pre-construction freeze: constructor attempts = 0, evaluated-agent outcomes
= 0, and actual V3 human reviews/files = 0. Construction may begin only after the
release is committed and the ledger is explicitly activated against that exact
commit and manifest hash.
