# Stage-1 objective feasibility screening v0.1

Protocol identifier: `stage1-objective-feasibility-v0.1`

This protocol applies to all eight records in
`github-python-2024-medium-001`. It collects facts without ranking, omission,
mechanism assignment, triplet construction, model execution, or treatment
access.

## Safety and execution boundary

- Fetch exactly the already-recorded full commit into a fresh bare Git
  repository with depth 1 and no tags.
- Disable terminal credential prompting and Git hooks.
- Do not check out files. Read bounded text-like blobs through `git show` only.
- Do not invoke repository code, package managers, builds, tests, containers,
  databases, services, GPUs, or model runtimes.
- Remove temporary bare repositories after evidence has been written.
- Process every candidate once in ascending source-list position.

The inspection records the exact Git commands and return dimensions. A
network/fetch error is `NEEDS_REVIEW`, not evidence that the repository fails a
scientific gate.

## Facts collected

For each candidate the inspector records:

- captured SPDX licence and matching licence-file paths/hashes;
- expected and resolved commit and Git-tree identities;
- captured default branch and language, extension counts, and statically
  declared Python/runtime constraints;
- apparent and allocated bytes of the bare depth-1 clone, plus logical tree
  bytes and entry counts;
- test directories/files, static Python test-function count, and detected
  test frameworks;
- package, build, dependency, lock, container, and CI metadata;
- deterministic setup-command candidates derived only from metadata paths;
- static signals across bounded source, test, documentation, and build text
  for external services, GPU, database, runtime network, and proprietary
  dependencies;
- a likely baseline-test command when framework evidence supports one; and
- whether clean installation appears statically plausible.

`NOT_DETECTED_BY_STATIC_SCAN` never means a requirement is proven absent.
Every result records scan limits and any paths skipped because they were too
large, exceeded the aggregate budget, or contained NUL bytes.

## Frozen automatic-gate rules

1. `usable_licence`
   - `PASS`: captured SPDX is neither `NOASSERTION` nor `OTHER`, and at least
     one licence file is present.
   - `NEEDS_REVIEW`: otherwise.
   - This static pass remains subject to later licence review; the inspector
     never emits `FAIL` for ambiguous licence metadata.
2. `immutable_commit`
   - `PASS`: the exact 40-hex commit fetches, resolves as `FETCH_HEAD`, and its
     Git-tree SHA equals the captured Git commit-object tree SHA.
   - `FAIL`: a successfully fetched object resolves to a different commit or
     tree.
   - `NEEDS_REVIEW`: fetch or object access fails.
3. `reproducible_setup`: always `NEEDS_REVIEW`; no installation is executed.
4. `deterministic_baseline_tests`: always `NEEDS_REVIEW`; no test is executed.
5. `manageable_task_size`: always `NEEDS_REVIEW`; raw repositories have no
   constructed task yet.
6. `no_proprietary_credentials_or_uncontrolled_service`: always
   `NEEDS_REVIEW`; static signals cannot prove absence or necessity.

Mechanism and validation gates remain `NOT_ASSESSED`. A candidate with any
`NEEDS_REVIEW` automatic gate remains `DISCOVERED`. Only a frozen automatic
gate `FAIL` authorizes exclusion, using the existing exclusion code for that
gate. No candidate can reach `AUTOMATIC_GATES_PASSED` under static-only
screening unless all six gates independently become `PASS` in later evidence.
