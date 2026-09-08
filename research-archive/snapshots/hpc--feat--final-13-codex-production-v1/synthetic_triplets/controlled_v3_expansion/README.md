# Prospective semantic expansion: six retained plus up to fourteen additions

This researcher-only release freezes 28 specifications, X01–X28, in numerical
order with four constructor invocations available per specification. The six
permanent families are F01, F02, F04, F08, F17 and F20. Their original files and
human-review resolution remain authoritative. All 14 historical rejected versions
remain rejected; none is repaired or resubmitted here.

The specifications are design inputs, not implementations, tests, reference
solutions, or human certifications. Construction has not started. A separate
construction-input release must first freeze the complete source/public/sealed
packages, exact constructor model and environment, validator, and pre-generation
semantic audits for the whole pool. This release must predate every constructor
invocation. The agent experiment is **not frozen** and no agent runs are authorized.

## Admission contract

Process in frozen order and complete each family's disposition before moving on.
Every invocation counts toward four, including failures and timeouts. Preserve all
attempts; keep the first machine-valid candidate only. Every such candidate goes
to both primary human reviewers independently, even after one rejects it. Seal
their judgments from one another until both are submitted. Use a third human only
when the nine-gate vectors disagree. The same unchanged candidate requires two
whole-contract human PASS endorsements: both primaries, or one primary and the
adjudicator. Never combine individual passing gates from different rejecting
reviewers into an admission. Human rejection is terminal for that specification.

Stop immediately at 14 additions (20 total). Serial processing leaves no later
candidates in flight. Otherwise finish the 28-specification pool and report an
incomplete cohort. The attempt cap, order and gate remain fixed regardless of yield.
Only a completed cohort permits a separate, later experiment freeze; no Git tag
is created by this workflow.

## Lessons applied before generation

The immutable historical resolution motivates G01–G12 in `protocol.json`:

- F06/F09/F12/R02/F14/F15/F18 exposed repair APIs or answer-bearing interfaces;
  the new audit inspects names, complete reachable helpers, scaffolds and messages.
- F07/F14 exposed the security witness through public tests; benign feature tests
  and sealed security assessment now have an explicit information boundary.
- F03/F11/F19 passed narrow checks while R left broader conditions insecure;
  every new specification defines full-condition obligations and fixed dimensions.
- F07 lost legitimate feature behavior; each new specification records the
  complete retained feature contract.
- R02's U was implausible; each specification must explain why direct reuse is
  natural, without discarding a conspicuous defining source step.
- F03/F19 had second mismatches; exactly one row of each trust matrix may change.
- F05/F16 and F07/R01 duplicated underlying transitions and repairs; reviewers
  compare semantic pairs with all earlier retained families, not only labels/hashes.

The pool omits origin-sensitive redirects (near F20), lease/token lifetime
extensions (near F02), lexical path confinement (near F04), output-context escaping
(near F08), cache partition keys (near F17), and frame-length bounds (near F01).
Filesystem object replacement, uninitialized bytes and identity equivalence have
explicit distinctions from those neighbors. Similarity notes are design claims to
challenge in review, not automatic exemptions from gate 9. Previously rejected
mechanisms may inspire new prospective specifications but no old version is revived.

## Verification and evidence format

From the repository root:

```sh
/opt/miniconda3/bin/python scripts/verify_synthetic_expansion.py --check
/opt/miniconda3/bin/python -m pytest -q tests/test_synthetic_expansion.py tests/test_synthetic_human_resolution.py
```

`freeze_manifest.json` binds protocol, specifications, review template and all
historical final-directory files. `admission_ledger.json` starts empty and is the
only evolving study record in this release. Future records must be append-only in
project custody, with prior snapshots retained in version control; local hashes
alone do not prove chronology or prevent an authorized editor from rewriting history.
The verifier is read-only and checks hashes, evidence bindings, ordering, attempt
caps, the dual-human rule, attrition and the stop boundary. It never executes a
candidate, launches a constructor, submits a review, or freezes an experiment.
It checks human attestations as records, not cryptographic proof of identity or
the substantive truth of a semantic judgment.

A future construction release uses schema `construction-input-release/1`,
`frozen_at_utc`, this specification `freeze_sha256`, `no_evaluated_outcomes: true`,
`owner_attestation`, `constructor` (model/version plus the frozen controls),
`inventory` (repository-relative path to SHA-256), and `packages` in X01–X28 order.
Each package binds `family_id`, `inputs` (source, memory, public, sealed, validator,
prompt and environment inventory paths), and `audit_path`. Each audit is a dated,
signed human/design-owner G01–G12 decision with evidence per gate. It does not
replace either later human candidate review. An audit failure retires that spec.

The ledger binds `freeze_sha256`, an optional `construction_release` file reference
(`path`, `sha256`), and ordered `families`. A family row contains `family_id`,
`attempts`, and `reviews`. Each attempt records `number`, `started_at_utc`,
`completed_at_utc`, `input_release_sha256`, `constructor`, `artifacts` (path-to-hash
inventory), a hash-bound `trace`, and a hash-bound `machine_report`. The report binds
`family_id`, `attempt_number`, `candidate_sha256`, `input_release_sha256`, the full
named `checks` map, and `machine_valid`. A candidate digest is SHA-256 of the sorted,
compact JSON artifact inventory. Timeout/crash attempts still need a report whose
full check map records failure and a preserved trace; they consume one attempt.
Valid candidate inventories contain exactly B/app/service.py, feature.patch and
security.patch under a common candidate directory. Reports are immutable evidence
from the separately frozen validator; this verifier does not substitute for it.

Review entries are hash-bound file references to completed copies of
`review_template.json`. The reviewer scope must list every family already retained
at that point. Adjudicator records identify and explain every disputed gate, and
postdate both primaries. All evidence stays researcher-side. Do not distribute this
directory, patches, reports, traces, sealed tests or reviewer judgments to evaluated
agents. The old v2 experiment template cannot authorize this new cohort.

## Reporting boundary

Current truth: the six-family resolution exists and 28 additional specifications
are prospectively ordered; zero new candidates have been constructed or admitted.
The 18–22 machine-valid planning range is an expectation only. The proposed paper
claim about “14 additional families … yielding 20 … before any evaluated-agent
outcomes” becomes usable only after completed admissions, immutable evidence and
a truthful outcome-blind attestation establish every part of that claim.
