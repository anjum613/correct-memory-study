# Correct-Memory / Trust-Shift V2 Methodology Repair

Date: 2026-09-01 (Australia/Melbourne)

## Decision

`NON_GPU_STUDY_READINESS = FAIL`

No scientifically valid V2 execution fixture can be constructed for any of the
six frozen families under the prospective mechanical-only construction rule.
Five families couple the requested behavior to the only frozen mechanism that
makes `p*` false. Djoser's exact reverse-source construction conflicts in the
focal serializer and requires researcher-selected conflict resolution.

Accordingly:

- V2 fixtures ready: `0/6`;
- treatment-blind task-completion endpoints ready: `0/6`;
- GPU qualification ready: `FALSE`;
- study run authorized: `FALSE`; and
- no model inference or GPU job was run.

The work did resolve independent non-GPU infrastructure defects: the three
incomplete snapshot families now have content-addressed V2-only reconstruction,
and OS-level agent isolation passes on this host.

## 1. Starting state and worktree

The authoritative inputs were read completely before any change:

- `artifacts/v2-preflight/v2-preflight-report.md`, SHA-256
  `e6a398d89aefc1f204282910a89609811413164fd6d6793d5663d6c3d3fd8177`;
- `artifacts/v2-preflight/readiness.json`, SHA-256
  `c7a8e67dfdaafb201baf92cf67f0988e805defb95e6effa2dbf0f2841f855837`.

Verified audit worktree state:

- branch: `feat/v2-audit-and-qualification`;
- final HEAD and report commit:
  `8ffde96394f5990be8ffb9167c802c8d71128323`;
- status: clean.

The requested repair worktree and branch did not exist. They were created at:

`/home/s224049759/projects/correct-memory-study-worktrees/v2-methodology-repair`

on branch `feat/v2-methodology-repair`, based exactly on `8ffde963...`.

The evidence/code HEAD used to generate readiness is:

`73adcf40e4515bd66ff429217bb20ebed16c47bc`

The final artifact commit is the commit containing this report; the final chat
response gives its exact hash.

## 2. Protocol interpretation

`HISTORICAL_FAMILY` remains the frozen S/C/I family, evidence, memory, task,
controls, and witnesses from V1.

`V2_EXECUTION_FIXTURE` would be a prospectively frozen starting repository
constructed after the V1 audit and before V2 inference. It would not be an
untouched historical commit unless the exact historical record established it.

If a valid design were found, V2 would be described as a **prospectively
redesigned replication/follow-up on the same frozen historical trust-shift
families**, not an exact rerun of the original execution fixtures. No valid
fixture was found in this repair.

## 3. Frozen evidence preservation

No path under `families/`, `results/raw/`, `runs/raw/`, `memories/frozen/`, or
`tasks/*/hidden_oracles/` differs between the audit HEAD and the evidence/code
HEAD. In particular:

- all six family identities are unchanged;
- S/C/I revisions and historical evidence are unchanged;
- every focal predicate and trust-shift classification is unchanged;
- source-memory bytes and provenance are unchanged;
- security witnesses and their semantics are unchanged;
- safe controls and historical safe-repair evidence are unchanged;
- task text is unchanged;
- V1 results, artifacts, and historical refs are unchanged.

The construction manifest is:

`v2/fixtures/construction/manifest.json`, SHA-256
`949a24fa139dede8a2ef013b3cc9262d9833953a0c838fa7311f382ae6ee4c01`.

It validates every memory and task hash against each frozen family package.
No model outcome information appears in its selection inputs.

## 4. Prospective fixture construction audit

The only allowed construction was an exact historical delta, its mechanical
reverse from I, or an exact naturally occurring historical state with the same
invalidated trust context. No hand-authored delta, hunk selection, model-outcome
selection, or new task was allowed.

| Historical family | Candidate `F` and attempted construction | Result |
|---|---|---|
| MCP Pinot | Exact target commit `160c456e^..160c456e`; C is its sole parent. Reverse the full HTTP/HTTPS dual-transport commit. | Reversal removes the unauthenticated network read-query route, the sole frozen reason `p*(I)=FALSE`; `p*(B_v2)` becomes true. The STDIO-only source memory is not an exact HTTP implementation delta. `BLOCKED_NON_IDENTIFIABLE_FIXTURE`. |
| ONNX | Exact target commit `474c0b64^..474c0b64`, introducing `download_model_with_test_data`. | Removing archive extraction removes both the requested behavior and the only content-directed write mechanism, restoring `p*`. The source memory contains only the earlier single-model loader. `BLOCKED_NON_IDENTIFIABLE_FIXTURE`. |
| Axios | Exact target commit `128d56f4^..128d56f4`, adding a localhost base to WHATWG URL construction. | The same base enables ordinary relative paths and resolves attacker-selected protocol-relative authority input. Removing it restores `p*`; retaining it leaves the task complete. The source procedure rejects relative input. `BLOCKED_NON_IDENTIFIABLE_FIXTURE`. |
| Aim | Target FastAPI migration `190b44c4`; C and I are separated by 12 commits. Attempt complete reversal or exact source-Flask mapping. | Full reversal removes the FastAPI context. Partial reversal selects migration hunks. Mapping Flask `send_from_directory` into FastAPI is a researcher-authored cross-framework implementation. `BLOCKED_NON_IDENTIFIABLE_FIXTURE`. |
| HTTPX | Target `7e6e3516` removes `allow_relative`; source `e6da325e` adds authority handling in `copy_with`. | Reversing either relative-state acceptance or no-op copying removes a necessary clause of the recorded unsafe state, restoring `p*`. Mapping old `httpx/models.py` to target `httpx/_models.py` is non-unique. `BLOCKED_NON_IDENTIFIABLE_FIXTURE`. |
| Djoser | Exact source commit `9e2248e6^..9e2248e6`, adding `LOGIN_FIELD`. Mechanically reverse it from I with `git merge-tree 9e2248e6 8f65bfff 9e2248e6^`. | Conflicts occur in `CHANGELOG.rst`, `djoser/conf.py`, `djoser/serializers.py`, `docs/source/settings.rst`, and `test_set_username.py`. The focal `TokenCreateSerializer` is conflicted. Resolving it would choose implementation behavior. `BLOCKED_NON_IDENTIFIABLE_FIXTURE`. |

The family order and detailed exact revisions are frozen in the construction
manifest. No subset was selected: the benchmark remains six families.

## 5. Trust-shift invariant

The frozen historical transition evidence revalidates:

| Family | `p*(S)` | `p*(C)` | `p*(I_unsafe)` | `p*(B_v2)` |
|---|---:|---:|---:|---|
| MCP Pinot | TRUE | TRUE | FALSE | NOT CONSTRUCTED |
| ONNX | TRUE | TRUE | FALSE | NOT CONSTRUCTED |
| Axios | TRUE | TRUE | FALSE | NOT CONSTRUCTED |
| Aim | TRUE | TRUE | FALSE | NOT CONSTRUCTED |
| HTTPX | TRUE | TRUE | FALSE | NOT CONSTRUCTED |
| Djoser | TRUE | TRUE | FALSE | NOT CONSTRUCTED |

For the first five families, the permitted full reverse makes `p*` true. For
Djoser, the focal reverse is not mechanically resolvable. Therefore
`trust_shift_preserved_by_family` is false for all six: this means no accepted
`B_v2` exists, not that the historical transition was changed.

## 6. Memory relevance and task wording

Every frozen memory remains source-correct in S and byte-identical. However,
the stronger V2 construction requirement also needs the memory to supply a
unique faithful delta which, when applied to `B_v2`, produces the insecure
faithful-reuse control. That requirement fails:

- MCP and ONNX memories precede the target functionality and do not contain its
  exact implementation delta;
- Axios's source procedure rejects the relative input the target task requests;
- Aim and HTTPX require non-unique cross-framework/cross-version mapping; and
- Djoser's relevant source delta conflicts in the focal target code.

No memory was shortened or rewritten, and no warning about security, `p*`, or
the trust shift was added.

All six original task files remain byte-identical. No task wording changed, so
no security cue was introduced and no exact task diff exists.

## 7. Task completion and control matrices

No treatment-blind `TASK_COMPLETION` endpoint was created because there is no
accepted `B_v2` on which to define newly achieved behavior.

The required prospective matrix is therefore:

| Family | V2 base | Empty | Irrelevant | Faithful source reuse | Safe control |
|---|---|---|---|---|---|
| All six | BLOCKED: no `B_v2` | BLOCKED | BLOCKED | BLOCKED | BLOCKED |

This is not a test failure hidden as a pass. It is the scientific construction
failure that keeps task-completion readiness at `0/6`.

For integrity, the historical V1 matrix was rerun without model inference from
committed inputs:

`artifacts/v2-methodology-repair/historical-control-matrix.json`, SHA-256
`85cdb2c0c889c4497e732509b2bcedc3501889a0948dded88134d372fa7f5109`.

All six historical unsafe/untouched states fail the unchanged security witness,
all six safe controls pass security, and all six safe controls pass unchanged
V1 functionality. Historical task completion remains
`BLOCKED_NON_IDENTIFIABLE`. These historical outcomes are not mislabeled as V2
fixture-control outcomes in `readiness.json`.

## 8. V2-only snapshot reconstruction

The V1 defect was caused by upstream files ignored by the parent repository's
generic ignore rules, not by arbitrary dirty output:

- Axios: 205 exact files across S/C/I, chiefly upstream `lib/`, `dist/`, and
  adapter certificate files;
- Aim: 22 exact files across S/C/I under upstream paths named `models`;
- HTTPX: 21 exact files across S/C/I under `tests/models`.

The builder verifies that every Git-visible file has identical bytes in the
preserved historical tree and captures only regular files absent from the clean
audit-HEAD tree. Deterministic tar metadata uses UID/GID/mtime zero and preserves
only normalized executable/non-executable modes.

Manifest:

`v2/fixtures/snapshot-overlays/manifest.json`, SHA-256
`09600ac7392ed80967e91126bea2e93fcdfa5c353cb47f0529f7805dc7707c8b`.

Content-addressed archives:

- `sha256-7bdc885ceb69621e99f72f4d628a476ea077583e68d6a79fa9d002b17b6e63a3.tar.gz`
  (Axios, 1,013,941 bytes);
- `sha256-3bd1f011a9ad78516c609599e81893d9983555695296cb39c59799db64f40ce4.tar.gz`
  (Aim, 38,870 bytes);
- `sha256-6c88e378035590d5310d0ca93e8c96a3c7d454a3caccfd00b38efa67170564a1.tar.gz`
  (HTTPX, 14,685 bytes).

`scripts/v2_reconstruct_snapshot.py` reconstructs any of the nine states from
the clean checkout and archive. It rejects absolute paths, `..`, duplicate or
undeclared members, non-regular entries, hash/size mismatches, existing-file
overwrites, clean-base mismatches, and final-digest mismatches.

All nine reconstructed repository digests exactly match the frozen V1 package
manifests. MCP, ONNX, and Djoser clean snapshots already match, so
`clean_snapshot_reconstruction_by_family` is true for all six.

V1 package trees and historical refs were not edited to make old tests pass.

## 9. OS-level isolation

Host inventory:

- Apptainer: absent;
- Singularity: `/usr/local/bin/singularity`, version 3.6.0;
- bubblewrap: absent;
- Podman: absent;
- `unshare`: `/usr/bin/unshare`, util-linux 2.37.2;
- unprivileged user namespaces: enabled;
- user+mount+PID+network namespace probe: pass.

The immediately usable mechanism is an unprivileged user, mount, PID, IPC, UTS,
and network namespace with a tmpfs root and chroot. Specification:

`configs/v2/agent-sandbox.json`, SHA-256
`12962378b188aa22d7172c0d91e4a96b2de1007f8e91a676053a3ea30e5b18f9`.

Launcher:

`scripts/v2_agent_sandbox.sh`, SHA-256
`7cd6ccfbcdc538c9342ed7f775fdf20fe9185f4d97abeeeacde5c2a84a6c6200`.

Visible mounts/environment:

- candidate at `/workspace`: read/write;
- `/usr` and `/opt/miniconda3`: read-only;
- isolated tmpfs `/tmp`, `/home/agent`, `/dev`, and new `/proc`;
- environment cleared to a six-variable allowlist;
- hidden evaluator outside the namespace;
- external network absent through a new network namespace;
- isolated loopback enabled for local tests.

Adversarial tests confirm failure for `../` traversal, absolute home access,
absolute and relative symlink escape, environment-secret extraction, known
witness/audit paths, another run's output, V1 project paths, root/user SSH
locations, user configuration/cloud-credential paths, runtime writes, and
external IPv4 connection. Candidate read/write and isolated loopback succeed.

`OS_SANDBOX = PASS` on this host. The GPU host must still run the same sandbox
qualification before live model qualification; this local pass is not a claim
about an untested rental host.

## 10. Context and prompt census

The V2 limits remain unchanged:

- `C = 32768`;
- `B = 16384`;
- `R = 256`;
- `G = 4096`;
- `S = 32`.

No task or wrapper changed. Qwen's exact 12 cells were regenerated through its
pinned tokenizer and are cell-identical to preflight after artifact-path
normalization. The Devstral 1.8.4 interpreter entered `autofs_wait`; no newer
serializer was substituted as qualification evidence. Because all rendered
task/wrapper/memory bytes are unchanged, the exact preflight 1.8.4 counts were
carried forward and independently matched cell-for-cell by a diagnostic
serializer run. The live exact recount is explicitly classified unavailable.

Artifacts:

- Qwen census SHA-256
  `f2d2e424a0e4a2f9d8e6e557ce048f733df8871cefb02827d8838bac552b5884`;
- Devstral census SHA-256
  `6407a105f562767d030ab8fd08fe1d2ba7ba0187449a9a7a18dcfe063ad02cc9`;
- validation SHA-256
  `c64d7e5cd2f9b2b4593804443d1e6f4ac5dd9537510880e1b4c99bb3b73f1235`.

All 24 cells satisfy `P + B + R <= 32768`. Memory was not shortened, no-memory
was not padded, and no compaction was added.

## 11. Test results and classification

Current results:

| Scope | Result |
|---|---|
| All `tests/test_v2_*.py` | 83 passed, 0 failed |
| Shared context, serialization-static, authorization, protected-path runtime | 172 passed, 0 failed, 2 exact Devstral tests unavailable |
| V2 snapshot overlay focused batch | 13 passed |
| V2 fixture/snapshot/sandbox combined focused batch | 38 passed |
| Final readiness/control/fixture/snapshot/sandbox focused batch | 44 passed |
| Historical incomplete V1 snapshot group | 6 passed, 12 failed unchanged |
| Python compilation | PASS |
| `git diff --check` | PASS |

JUnit evidence:

- `pytest-v2-required.xml`, SHA-256
  `876599245d8f5d4ff56d6c277c9c9445552d07d84f2775832c88189040c1c5e1`;
- `pytest-shared-required.xml`, SHA-256
  `0b484ea5f8b8ebbb9a406e1498ae0f8af9877331b9b2a34373a3f0b69e22051d`;
- `pytest-v1-incomplete-snapshots.xml`, SHA-256
  `dda399cc53e0e24e062b8d68895a9959814ad27b0b3e9d3d3a1ca9233356b719`.

Classification artifact:

`artifacts/v2-methodology-repair/test-classification.json`, SHA-256
`0f5a940a1a49898058b3d559ddaa69556bf1a8ab0b6d982c97fe8f24e8c17b0b`.

It classifies every preflight failure:

- 13 incomplete-snapshot assertions:
  `V1_IMMUTABLE_HISTORICAL_TEST`; V2 overlay equivalents pass;
- 2 job-25692 assertions: `V1_IMMUTABLE_HISTORICAL_TEST`;
- 4 frozen interpreter/mount timeouts:
  `EXTERNAL_FROZEN_ENVIRONMENT_UNAVAILABLE`;
- 68 unexecuted preflight tests:
  `NETWORK_STORAGE_INFRASTRUCTURE_FAILURE` as an aggregate because no per-test
  completion evidence exists;
- 2 current exact Devstral tests:
  `EXTERNAL_FROZEN_ENVIRONMENT_UNAVAILABLE`.

There is no unresolved `V2_LOGIC_FAILURE` or `V2_FIXTURE_FAILURE` in the code
that could be fixed without inventing a fixture. Scientific non-identifiability
is recorded separately and is not mislabeled as a passing fixture test.

`v2_required_tests_pass = false` because actual six-family V2 fixture/control
tests cannot exist at 0/6 fixtures and the two exact pinned Devstral tests did
not execute. `full_repository_suite_pass = false`; the historical suite was not
redefined.

## 12. Readiness fields

The authoritative machine-readable result is:

`artifacts/v2-methodology-repair/readiness.json`, SHA-256 at generation time
`cf9f6fe90ea46fcc10ae5d380a9611c85165ab55e06a107cdf110ec365969aea`.

Key decisions:

- `v1_immutability_preserved = true`;
- `six_family_identity_preserved = true`;
- `source_memories_preserved = true`;
- `security_witnesses_preserved = true`;
- all six clean snapshot reconstructions: `true`;
- all six V2 fixture/task-completion fields: `false`;
- `all_prompts_fit_32768 = true`;
- `v2_required_tests_pass = false`;
- `full_repository_suite_pass = false`;
- `os_sandbox_status = PASS`;
- `non_gpu_study_readiness = FAIL`;
- `gpu_qualification_ready = false`;
- `study_run_authorized = false`.

## 13. Remaining non-GPU blockers

1. MCP Pinot: reversing the only exact target delta restores `p*`; source memory
   is not the HTTP implementation delta.
2. ONNX: archive extraction is both the requested behavior and the recorded
   unsafe write mechanism.
3. Axios: the localhost base is both relative-path support and the authority
   trust invalidation.
4. Aim: complete reversal removes FastAPI; partial/cross-framework mapping is
   researcher-selected.
5. HTTPX: relative acceptance/copying are necessary to both the task and the
   recorded unsafe state; cross-version mapping is non-unique.
6. Djoser: exact reverse-source construction conflicts in the focal procedure.
7. Two exact Devstral tokenizer tests are unavailable in the frozen autofs
   environment.
8. The immutable historical full repository suite is not PASS.

The first six are sufficient to keep the study scientifically unrunnable.
Renting GPUs cannot resolve them.

## 14. GPU status and engineering minimums

No A100 or other GPU job was submitted. No Qwen, Devstral, or six-family model
inference ran. Both live qualifications remain `NOT_TESTED_NO_GPU`.

Engineering minimums remain unchanged from preflight:

- Qwen2.5-Coder-32B-Instruct: estimated 75.13 GiB at 32K/concurrency 1;
  use 94 GB TP1 or two 80 GB GPUs at TP2;
- Devstral-Small-2507: estimated 53.30 GiB at 32K/concurrency 1; use 80 GB TP1.

These are capacity estimates, not authorization to rent or run. Because
`NON_GPU_STUDY_READINESS = FAIL`, `GPU_QUALIFICATION_READY = FALSE`.

## 15. Commits

Coherent implementation commits:

1. `e16eb5447` — Add reproducible V2 snapshot overlays
2. `7de390a42` — Add OS-level V2 agent sandbox
3. `fc466ce57` — Record six-family V2 fixture construction audit
4. `4da368230` — Use V2 overlays for historical control checks
5. `73adcf40e` — Add conservative V2 methodology readiness decision
6. Final artifact commit — commit containing this report and readiness artifacts

Nothing was merged into V1.
