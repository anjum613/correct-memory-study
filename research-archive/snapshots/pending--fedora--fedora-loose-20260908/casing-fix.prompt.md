You are fixing one narrowly scoped correctness issue in the current candidate-discovery repository.

CONTEXT

The previous dependency-order bug has already been fixed and committed.
Do not modify or redesign that fix.

A separate latent bug remains:

- GitHub GraphQL may identify a repository as ExampleOwner/ExampleRepository.
- REST-derived/materialization identity may be exampleowner/examplerepository.
- Evidence keys are case-sensitive.
- Capture and materialization can therefore construct different logical keys
  for the same GitHub repository.
- Valid linked-pull-request evidence may become unreachable during materialization.

This must be fixed before another live candidate-discovery run.

STRICT FILE SCOPE

You may modify only:

src/cmpilot/candidate_discovery_v03.py
tests/test_candidate_discovery_v03.py

Do not modify or create any other repository file.

Do not stage or commit anything.

PROHIBITED

Do not:

- access GitHub or any network service;
- use web search;
- use curl, wget, gh, SSH, SSHFS, Slurm, sbatch, srun, GPUs, or HPC;
- install or upgrade packages;
- run candidate discovery;
- modify stopped-run evidence or manifests;
- change search queries;
- change source definitions;
- change candidate identities;
- change scoring or ranking;
- change trust-family or triplet logic;
- change scientific selection rules;
- change rejection classifications;
- change provenance requirements;
- change HTTP 404/410 semantics;
- change rate-limit semantics;
- globally lowercase unrelated evidence keys;
- perform unrelated cleanup or refactoring;
- change Git history.

INVESTIGATION

Trace the production code for:

1. linked-PR evidence-key construction during capture;
2. linked-PR evidence lookup during materialization;
3. GraphQL nameWithOwner handling;
4. REST owner/repository handling;
5. existing repository-identity helpers;
6. persisted evidence-key compatibility.

Identify the precise point where differing repository casing can produce
different logical keys.

IMPLEMENTATION REQUIREMENTS

Make the smallest safe change so that capture and materialization resolve the
same logical repository identity when only casing differs.

Preserve original accepted GitHub casing in request/response/evidence/provenance
where the existing implementation currently preserves it.

The fix must preserve:

- same-casing behaviour;
- the existing ClosingPullRequests-before-repository-metadata dependency order;
- GITHUB_REPOSITORY_UNAVAILABLE behaviour;
- HTTP 404/410 handling;
- retry/rate-limit behaviour;
- existing scientific selection behaviour;
- existing persisted capture compatibility.

RAW_CAPTURE_INCOMPLETE must not occur solely because REST and GraphQL used
different casing for the same repository.

Do not globally normalize all evidence keys.

If a correct fix requires changing the persisted evidence-key schema, STOP
rather than implementing that schema change.

REGRESSION TEST

Add production-path regression coverage where:

GraphQL:
    ExampleOwner/ExampleRepository

REST/materialization:
    exampleowner/examplerepository

with the same linked pull-request number.

Prove that:

1. materialization reaches the captured linked-PR evidence;
2. RAW_CAPTURE_INCOMPLETE is not raised because of casing;
3. the result matches an equivalent same-casing control;
4. no duplicate accepted logical evidence is created solely due to casing;
5. original accepted casing remains preserved where currently expected;
6. the existing dependency-order regression still passes.

Use existing production helpers and fixtures rather than creating a simplified
replacement implementation.

CHANGE LIMIT

Keep the production change small.

If this appears to require roughly more than 120 modified non-test lines,
STOP and explain the architectural issue instead of performing a broad refactor.

VALIDATION

Run only local validation.

Run:

1. the new casing regression;
2. relevant linked-PR tests;
3. python -m pytest -q -p no:cacheprovider tests/test_candidate_discovery_v03.py
4. python -m py_compile src/cmpilot/candidate_discovery_v03.py
5. git diff --check

Do not run the full repository suite.
We will compare that separately against the already recorded 25-failure baseline.

Do not access the network during validation.

FINAL REPORT

Report:

- exact root cause;
- capture-side key construction before the fix;
- materialization-side key construction before the fix;
- exact change made;
- functions changed;
- tests added;
- commands run and results;
- git diff --stat;
- any remaining risk.

Before finishing, verify that only the two permitted files are modified and
that nothing is staged.

End with exactly one of:

READY_FOR_REVIEW

or

STOPPED: <reason>

Do not stage or commit.
