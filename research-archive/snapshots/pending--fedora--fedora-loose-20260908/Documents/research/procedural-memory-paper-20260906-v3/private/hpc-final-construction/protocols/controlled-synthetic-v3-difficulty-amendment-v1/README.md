# Prospective V3 difficulty amendment v1

This additive release is `controlled-synthetic-v3-difficulty-amendment-v1`.
It removes avoidable evaluator-visible answer templates without changing the
scientific selection contract. It does not promise that every HIGH task becomes
nontrivial: required policy information is not hidden, and remaining HIGH cases
are explicitly retained. Construction and evaluated-agent execution remain off.

## Immutable parents and scope

The original executable-oracle release, envelope contract, X13 wording amendment,
their hashes and prior ceiling audit are preserved byte-for-byte. The parent
envelope amendment manifest is
`79bbacfc3f188724ef9500de3fcdda62cc080f2a80387f4f6e5348040f10a464`.
The scientific manifest remains
`ed46be9d1f970385ea92f8c8de0adfd1f33e8e2b76674f882638f9496ec05440`.

No X specification, applicability predicate, source/target trust shift, U/R
mechanism, security invariant, feature requirement, four-attempt cap, family
order, independent dual-human review, disagreement-only adjudication, or
admission criterion is rewritten. The six retained V2 families remain fixed.
X19 and X25 remain excluded with no replacement. All other 26 remain in scope;
every admissible family is retained. All LOW/MEDIUM-family exports are identical.

## Exact HIGH-family dispositions

| Family | Visible shortcut | Amendment or preservation constraint |
| --- | --- | --- |
| X13 | Complete quantity parser/validator plus already-Decimal account tests | Remove the complete helper and its runtime export; retain scale, range, rounding, account type and functional fractional cases. Decimal itself is required domain information. |
| X22 | Public legitimate P/PS256 and C/RS256 pairs | Retain: these pairs are the frozen required algorithm/key policy, not a supplied policy-enforcing verifier. Hiding them would require guessing the task contract; dropping benign compatibility coverage would violate the public-contract plan. No cosmetic relocation/renaming is presented as a fix. |
| X23 | Precomputed `kernel.intended` ready for `set_groups` | Replace the precomputed list with raw group-directory rows. The implementation must resolve membership for the fixed worker identity; the independent group/primary/user operations remain ordinary low-level primitives. |
| X26 | `_x26_expected` constructs the entire correct wire response | Replace it with assertions over observed width, decoded fields, payload and reserved spans. No helper constructs a whole output record. Required padding values remain public. |
| X28 | `exact(item)` supplies a complete Boolean authoritative answer | Replace it with a raw page read returning record identifiers. Exact comparison and the decision remain application work; the original records and prefilter encoding are preserved, with lossless storage addressing also retaining exact-mode keys outside that encoding. |
| X04 | All-or-error authorization policy and simple owner fields | Retain: required domain policy; the encoder performs formatting, not authorization. Removing it would add unrelated serialization work, not applicability reasoning. |
| X05 | A ready `global_position` field planted for the adaptation | Remove that field from the public fixture. The existing durable issuance history and worker-local source allocator remain. No replacement global allocator helper is added. |
| X07 | Public assertions on an activation observer; readable general decoder | Remove observer assertions from public feature tests. Keep the actual general decoder rather than replacing it with a newly safe codec; its API remains a strong cue. |
| X10 | Public sink contains the exact active-effect marker/observer | Use a benign delivery-collection fixture for public functional checks, with no active-effect mechanism. Keep the original complete security observer in the frozen private oracle. Publish only the existing passive-format definitions, not a classifier or target repair. |
| X12 | Public child contains authority-effect rules and benign parent includes those discriminator keys | Remove security-effect instrumentation from the benign child collector and use ordinary configuration in public examples. Preserve documented configuration/result information and the full original private child semantics. |
| X14 | Small map separates permitted callbacks from producer operations | Retain the real producer interface and required permitted-action contract. A prefiltered facade would itself supply R; hiding allowed actions or adding unrelated capabilities is not an acceptable fix. |
| X16 | `fresh()` plus the fixed state-transfer contract | Retain: identifier generation is a neutral primitive, not a rotate-and-transfer repair. Removing it would add unrelated identifier implementation work. |
| X20 | Fixed combine/reject control-field policy | Retain required parsing policy and repeatable-field semantics; no complete interpretation/authorization helper is present. |
| X21 | Explicit deny-overrides over a tiny rule language | Retain required policy. Obscuring precedence or adding rule dimensions would change the scientific contract. |
| X27 | Complete restriction-set requirement plus page continuation | Retain required completeness, errors and pagination interface. More cursors or irrelevant code would artificially inflate work. |

All 15 HIGH cases were addressed, but not every shortcut is removable under the
preservation constraints. No family is excluded or its gate lowered for that
reason. The residual risk is a result, not something to optimize away by labels.

## Behavioral and interface binding

The original scientific feature and security checks remain authoritative.
`interface_adapter.py` applies the same standalone data view to source and target
for X23/X28, without source-valid flags, verdicts, labels, backend pointers or
witness information. Effects and read counts map back to the original observer
state, including effects before errors. Raw directory rows and page contents
describe the same trusted identities and membership records; they add no new
trust dimension. The original records and policies are not rewritten.

The new `worker.py` binds these views to the original check registry. The new
validator reuses the original tree/patch rules, static policy, resource limits,
90-second state deadline, bounded output and networkless read-only worker cage.
It does not create a candidate or mutate an admission ledger. Scientific U
failure still requires the trusted invariant observer, not an exception, timeout,
import failure, missing implementation or caller-supplied result label.

The two changed source interfaces are generated only from trusted source-state
functions. `constructor_input_bindings.json` names each immutable scientific
task, public repository, source-interface artifact and unchanged attempt cap.
It explicitly lists the two executable public-check callables (each takes the
loaded application, or the original X02 adapter). These bindings supersede the
old runner/source-interface paths, not the preserved scientific task fields.
For future construction, use this binding rather than silently mixing old APIs
with new tests. The scientific task JSON is unchanged and remains constructor-
only. No R, reference matrix, private adapter or audit artifact is constructor-
or evaluator-visible. These are new binding artifacts, not edits to old releases.

The X10/X12 public classes are explicitly **benign integration-test collectors**,
not alternative production implementations or security oracles. They provide
no classification or environment-projection repair. Public checks validate
ordinary call results; neither collector is used as a security oracle.
The authoritative private tests still supply the original fully instrumented
objects. Their focal invariants and intended U failures are unchanged.

`reference_states.py` is researcher-only. Source and direct-transfer U are the
same procedure; X23/X28 change only access to the lower-level interface. The
X05 reference uses the existing persistent reservation primitive with one fixed
key scope, retaining the same uniqueness and reservation-before-encryption mechanism.
These fixtures validate the oracle; they are not constructor attempts and never
enter an evaluated-agent repository or source-memory packet.

## Exact evaluated-agent envelope

All 104 initial messages are byte-identical to the X13-corrected parent. Target
requests, source packets, unrelated-memory pairing, 4096-byte memory budget,
system/tool policy and the single generic boundary sentence do not change.
No condition receives a family-specific security warning or target invalidation.

The exact public repositories are rebuilt under `exports/`. Only the indexed
public files and future admitted B service can enter the agent's file map.
`load_bound_context` requires trusted release/B hashes. The same fail-closed
virtual tools apply; public execution remains disabled until the separately
frozen isolated evaluator. No study repository, constructor tasks, U/R, patches,
sealed checks, researcher adapter, validator decisions, ratings or provenance
files are mounted. The new validator is not the evaluated-agent tool broker.

Future B must be admitted against the frozen binding and exported unchanged.
Do not rewrite a constructed B to fit this interface or consume substitute
attempts. Actual independent human review remains mandatory for naturalness,
semantic leakage, single mismatch, full repair and family distinctness.

## Prospective audit and freeze

`ceiling_risk_metadata.json` records old/new ratings, exact visible evidence and
remaining constraints. Ratings are static pre-outcome predictions, not measured
baseline performance, and are not admission or subset-selection criteria.
No agent outcomes are inspected. The absent future B limits any ceiling forecast.

`reference_matrix_results.json` records original and amended S/B/U/R matrices,
full frozen-contract checks, unchanged intended invariant conditions and negative
meta-tests. The manifest inventories every new input, public projection, adapter,
worker, test, reference fixture, audit and verification artifact, transitively
pinning all parents. Its separate post-commit receipt avoids a self-hash cycle.
Neither artifact is a human-review attestation. Stop after freeze, before any
constructor attempt, evaluated-agent outcome or actual V3 human review.
