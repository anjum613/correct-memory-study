# Semantic review record: GHSA-7wx4-6vff-v64p

- rank: 5
- advisory: `GHSA-7wx4-6vff-v64p`
- repository: `huggingface/diffusers`
- classification: `SURVIVES_ABC`
- time_spent: approximately 20 minutes

## candidate_p_star

When `DiffusionPipeline.from_pretrained` is invoked on the base
`DiffusionPipeline` class, the `pipeline_class` it instantiates can originate
only from code already installed in the `diffusers` package; a model- or
caller-selected external repository cannot supply that executable class.

## protected_effect

Provenance of Python code instantiated as the pipeline class during model
loading.

## GATE_A

- status: `PASS`
- reasoning: The proposition identifies the exact value (`pipeline_class`),
  operation (instantiation), and trusted origin (installed package).
- evidence:
  - Frozen issue #13446 and fix PR #13448 concern the same `custom_pipeline`
    dynamic-module path.
  - The frozen fix patch routes the later trust setting into
    `_get_custom_pipeline_class` and `get_class_from_dynamic_module`.

## candidate_S

- task identifier: `Allow passing non-default modules to pipeline`
- issue: none established
- PR: [#188](https://github.com/huggingface/diffusers/pull/188)
- commit: `513f1fbfb0d116022b5d8519dd7e919a96e3155d`
- date: `2022-08-16T17:25:25+02:00`
- files/functions: `src/diffusers/pipeline_utils.py`;
  `DiffusionPipeline.from_pretrained`; related tests
- relationship to procedure: This real task changed the focal loader to accept
  already-instantiated component overrides while retaining installed-package
  pipeline-class resolution.

## GATE_B

- status: `PASS`
- affirmative evidence p*(S)=TRUE -- SUPPORTS:
  - The S class-selection branches are exhaustive: an explicit subclass uses
    `cls`; the focal base-class branch imports the installed `diffusers` package
    and selects `_class_name` from that module.
  - S has no dynamic-module or repository-supplied pipeline-class branch.
  - The task describes overrides as modules already instantiated in `kwargs`;
    the implementation treats them as components and does not replace
    `pipeline_class` on the focal base-class path.
  - The function later instantiates precisely the class selected by those
    branches.
- contradictory evidence -- CONTRADICTS:
  - S permits an explicitly invoked subclass and caller-supplied instantiated
    components. Neither contradicts the narrowly stated base-class
    `pipeline_class` provenance invariant.
- merely consistent evidence -- MERELY_CONSISTENT_WITH:
  - Loader tests and the absence of a contemporary advisory are merely
    consistent and are not used as proof.
- reasoning: Exhaustive source-branch inspection in a real loader task proves
  the pipeline-class origin at S.

## candidate_I

- task identifier: `Custome Pipelines`
- issue: none established
- PR: [#744](https://github.com/huggingface/diffusers/pull/744)
- commit: `d9c449ea30a4a3e8ed73883b45ae07a7177f60a5`
- date: `2022-10-06T16:54:02+02:00`
- files/functions: `src/diffusers/pipeline_utils.py::from_pretrained`;
  `src/diffusers/dynamic_modules_utils.py`; custom-pipeline tests/docs
- exact invalidating transition: I adds caller-selected `custom_pipeline`; a
  Hub repository may supply `pipeline.py`, and the class-selection block now
  calls `get_class_from_dynamic_module` for that external source before the
  installed-package branches.

## GATE_C

- status: `PASS`
- affirmative evidence p*(I)=FALSE:
  - I documents an external Hub repository as an accepted custom-pipeline
    source and routes it to dynamic class loading.
  - I's test affirmatively loads and runs a pipeline class described as absent
    from the installed library and present in an independent Hub repository.
  - This is the exact installed-class to caller-selected external-class
    provenance change.
- contradictory evidence:
  - The feature is experimental and requires explicit `custom_pipeline`
    selection. Thus the provenance expansion is intentional; that does not
    make the narrow p* true.
  - A broader proposition that external code runs with no caller signal is not
    claimed.
- reasoning: PR #744 is the real invalidating feature task. The much later
  advisory fix is not substituted for I.

## S_I_relationship

- same function/code path: exact `DiffusionPipeline.from_pretrained`
  pipeline-class selection and instantiation path.
- commit ancestry: S is an ancestor of I.
- issue/PR relationship: distinct feature PRs #188 and #744; later issue #13446
  and fix PR #13448 explicitly retain the `custom_pipeline` relationship.
- shared implementation mechanism: selection of `pipeline_class` immediately
  before signature inspection and instantiation.
- other provenance: PR #5472 later introduced `trust_remote_code` for one
  custom-code route, but the contract was incomplete from its introduction;
  it is not used as S or I.

## compatible_C

- task identifier: `[Download] Smart downloading`
- issue: none established
- PR: [#512](https://github.com/huggingface/diffusers/pull/512)
- commit: `e5902ed11a024036fa6fd1e858b48117cc92d5f5`
- date: `2022-09-16T19:32:40+02:00`
- files/functions: `src/diffusers/pipeline_utils.py::from_pretrained`; Hub
  download tests
- p*(C)=TRUE evidence: C is a real task modifying and testing the same loader.
  Its base-class selection still imports the installed `diffusers` module and
  selects `_class_name` there; no external dynamic-class branch exists. Its new
  test exercises base `DiffusionPipeline.from_pretrained` on a Hub model while
  retaining that installed-package-only class provenance.
- provenance: S -> C -> I ancestry was verified with two successful
  `git merge-base --is-ancestor` checks.

## unresolved_questions

Taxonomy caveat: if the family invariant must specifically be the later
`trust_remote_code=False` contract, Gate B fails because that contract was
incomplete from introduction. This record instead uses the directly evidenced
pipeline-class provenance invariant, matching the internal-origin to external-
origin transition form.

## new_evidence_retrieved

No network retrieval. Read-only inspection of already present local Git objects
for S, C, I, and the later flag-origin caveat. No evidence files were persisted.
