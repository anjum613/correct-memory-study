# Controlled V3 construction V3 operational protocol

This is a separately versioned construction-interface protocol. It does not
amend any scientific specification, family order, exclusion, canonical test,
deterministic validator, evaluator envelope, difficulty label, human-admission
criterion, attempt cap, or first-admissible rule in
`controlled-synthetic-v3-difficulty-amendment-v1`.

## Constructor interface

For one family and one attempt, the constructor receives the unchanged frozen
scientific task, its frozen source procedure, the frozen public repository, and
an explicit `interface.json`. It authors exactly two UTF-8 service components:

* `components/neutral_target/app/service.py` (or `service.csirpy` for X02): the
  target baseline that preserves existing behavior and leaves the requested
  feature unavailable.
* `components/functional_target/app/service.py` (or `service.csirpy` for X02):
  the complete target implementation satisfying existing behavior, the feature,
  and every frozen full-target obligation.

The constructor is not asked to author the synthetic U state or either patch.
The trusted local adapter uses the already-frozen canonical source-context
implementation as U and mechanically derives `B/`, `feature.patch` (B to U),
and `security.patch` (U to R). The unchanged frozen validator then evaluates the
same B/U/R matrix and admission rule as before.

The per-family interface enumerates every allowed import root/module pattern and
every exact output path. `fixture_api`, `math`, `threading`, and any unlisted
module are not candidate imports even when a similarly named read-only public
fixture exists.

## Runtime containment

Codex executes behind one external user/mount/pid namespace and chroot. Its
internal bubblewrap sandbox is disabled only inside that external containment.
The host devpts mount is bound once. There is no nested bubblewrap namespace and
no nested devpts mount. Scientific inputs are bind-mounted read-only; only
`components/` and `.scratch/` are writable.

Constructor model/runtime identity is operational metadata, not a scientific
variable or admission criterion.

## Security-witness boundary

No researcher test, reference state, sealed witness, evaluator outcome, human
judgment, or ceiling-risk label enters the constructor workspace. The component
adapter does not import or read researcher/reference modules. Security witnesses
remain local, deterministic, non-operational inputs to the unchanged frozen
validator.

## Start gate

No X-family attempt may start unless all of the following are true:

1. the frozen scientific bindings and hashes verify;
2. the component interface verifies;
3. the static one-boundary runtime preflight passes;
4. one non-benchmark dummy constructor writes the exact two component forms;
5. the local adapter derives and reapplies B/U/R exactly; and
6. the signed-by-content dummy receipt records `PASS`, zero X-family attempts,
   zero evaluated-agent outcomes, and zero human reviews.

The dummy uses no family ID, benchmark task, public test, validator witness, or
reference state and never counts against an X-family attempt cap.

## Selection and stopping

Families remain in frozen order X01–X18, X20–X24, X26–X28. X19 and X25 remain
excluded with zero attempts. Each in-scope family has at most four attempts.
The first candidate passing the complete unchanged validator is retained and no
later candidate is generated. Four failures yield `CONSTRUCTION_EXHAUSTED`.
