# SusVibes Target-Substrate Feasibility Report

## Decision

`SUSVIBES_TARGET_SUBSTRATE_READY = TRUE`.

SusVibes v1.0 provides a scientifically usable, eligibility-screened target substrate for applicability-aware procedural transfer. Four of five prospectively selected official-sample targets satisfy the strict five-state task matrix; all five satisfy the decisive U/R focal-security matrix and executable feature-retention gate. The Wagtail development target is excluded because masking the imported symbol causes the unchanged test command to abort during collection. Under the frozen rule that is `INFRASTRUCTURE_INVALID`, never task failure. This isolated failure is not the fundamental task-identifiability failure observed in SecureVibeBench.

This decision authorizes neither unseen screening nor source matching. No evaluated coding model, Qwen, Devstral, GPU, source corpus, source matcher, confirmatory memory, or confirmatory target was run or built.

## Original repository and worktree audit

At `2026-09-02T08:00:42Z`, the original repository at `/home/s224049759/projects/correct-memory-study` was on branch `feat/mini-swe-agent-smoke` at `a146b62399c049b8723373752b96a621ee174c95`. Its status was `DIRTY_PRE_EXISTING_UNTRACKED` with 12 pre-existing untracked entries; none was changed. The complete 27-entry `git worktree list --porcelain` snapshot is frozen in `repository-worktree-audit.json`.

Both required preserved commits exist: `31cafe2cf794a3b737f491b9fd0a35e827de3db1` and `26100c2882e3213909d82654a6b138dfc713fda7`. This isolated worktree was created at `/home/s224049759/projects/correct-memory-study-worktrees/v2-context-dependent-memory-susvibes-feasibility` on `feat/v2-context-dependent-memory-susvibes-feasibility`, based on the latter commit.

## Frozen source and cohort

- Official repository: `https://github.com/LeiLiLab/susvibes`
- Release: `v1.0`
- Commit: `7e1b4b05240e56dc2b4e8253b2cc5c9481d016f3`
- Tasks: `186` (verified from the release dataset)
- Dataset SHA-256: `0cb5fbffe7ba59a8e16d42c293944bdd8e1e23795941a4b496ac1043722b9550`
- Official release language distribution: Python 186/186
- Repository count by unique `project`: 101
- License: MIT
- Development targets: 5, frozen from the official sample before inspection
- Unseen universe: 181; only `instance_id` was enumerated

## Actual B/U/R construction

The pinned `base_commit` is R, the real security-fix commit. SusVibes splits its diff into production `security_patch` and test/configuration `test_patch`, reverses them to form U, and applies an adaptive `mask_patch` to U to form B. The task statement is generated from `mask_patch`; it is not independently authored. The published evaluation image contains B, dependencies, the original ordinary tests and image command, but not the focal `test_patch`; Git history is replaced by one initial commit.

- B: pinned published task-image `/project`, requested implementation masked.
- U: B plus `reverse(mask_patch)`.
- R: B plus `golden_patch`.
- U→R: exact `security_patch` applied to a clean U must equal R by non-Git tree hash.

All five cases have distinct B/U/R hashes and exact U→R equality. No exact vulnerable implementation, secure patch, patch artifact, CVE/CWE/GHSA label, or original history was found in B. Task statements do describe requested behavior and sometimes safety-relevant expectations, which must remain part of the frozen public target treatment.

## Evaluation evidence

| Gate | Result |
|---|---:|
| Strict task matrix | 4/5 PASS |
| FOCAL_SECURITY U-/R+ | 5/5 PASS |
| Feature retention | 5/5 PASS |
| Masking semantics | PASS |
| Oracle firewall | PASS |
| Container runtime | PASS |

The functionality evaluator applies only the candidate/state patch and runs the exact image command. The focal-security evaluator starts from a separate clean materialization, applies the exact official `test_patch`, then the state patch, and runs the same command/parser with SusVibes's carried threshold. These are independent executions, although focal security is an incremental suite rather than a globally independent security audit. `FOCAL_SECURITY` is therefore the only supported term.

The five U functionality runs pass, five R functionality runs pass, five U focal-security runs fail, and five R focal-security runs pass. B focal security is not used as an eligibility requirement because a missing focal feature can also break collection or ordinary tests.

## Infrastructure attempts

Every completed raw log is retained. Django's initial run lacked `/dev/shm`; Requests initially lacked namespace hostname resolution, and its second attempt used network isolation inconsistent with official Docker defaults. Each was classified and retained as `INFRASTRUCTURE_INVALID` before a fresh, labeled retry. Accepted retry B/U/R hashes exactly match the earlier reconstructions. Singularity SIF archive hashes can differ across conversions, so the Docker manifest digest and extracted tree hashes—not the derived archive hash—are the reproducibility locks.

Docker, Apptainer and Podman are unavailable. Singularity 3.6 can pull and expand the five pinned images but cannot execute directly because its compiled session path is absent. The working adapter uses a read-only expanded rootfs, private user/mount/PID/IPC/UTS namespaces, private `/tmp`, `/root`, `/dev` and `/dev/shm`, a read-write `/project`, and host-equivalent evaluation connectivity matching SusVibes's Docker API call. The B-only agent firewall remains separately network-isolated.

Observed peak test-process RSS was 172.0 MiB and peak CPU was 138%. The HPC exposes 32 CPUs and 95.6 GiB currently available RAM. The Ceph worktree filesystem has 1266.1 TB free; local `/tmp` has 44.4 GB free. Quota tooling and reliable Ceph free-inode counts are unavailable.

## Cost extrapolation

- Serial full 186-target screening estimate: 40.61 hours.
- Retained storage estimate for 20 targets: 39.66 decimal GB.
- Retained storage estimate for 40 targets: 79.31 decimal GB.

These are point extrapolations from five heterogeneous development targets and exclude evaluated-model inference. Wagtail dominates runtime. Screening should be sequential or use bounded batches; the official source lock separately records the benchmark's 300 GB full-run recommendation.

## Oracle firewall and B-only boundary

The persistent public root is `targets/public/susvibes-development`. It contains only the task statement, public identity/language/project/image metadata, B hash and a B reconstruction descriptor. The explicit fixed `base_commit` field, U, R, vulnerable/safe patches, security patch, exact focal tests, CVE/CWE metadata, thresholds and evaluator outcomes are under `oracle_sealed/susvibes-development`. The official public instance ID and image name unavoidably retain an opaque commit-shaped suffix; the matcher is network-isolated and receives no mapping from that suffix to R.

All five public roots passed adversarial absolute-path and relative-traversal attempts under the qualified V2 OS sandbox, plus semantic leakage checks. The future matcher must be launched with only the relevant public root; it must never receive the feasibility artifacts or sealed root.

## Reproducibility

Each accepted case records the benchmark revision, canonical instance-record hash, B/U/R tree hashes, exact official/runtime evaluator composite hashes, Docker manifest digest, execution commit, commands, log paths and log hashes. The official SusVibes checkout was clean at every runner start. The research worktree was committed before each accepted execution; generated evidence was not used to choose targets or memories.

## Verification

The final SusVibes, V2 sandbox/preflight/prompting, and transient-snapshot regression suite passes 51/51. The protected-oracle snapshot suite passes 7/7. Python compilation, shell syntax, JSON parsing, and `git diff --check` pass. A repository-wide `pytest -q -x` reaches 48 passes and then fails on the pre-existing frozen AIM compatible-repository hash mismatch; no AIM/family file is modified here. An earlier unconstrained full run was aborted after the historical project-snapshot test copied ignored container runtimes and hit quota; both snapshot implementations now exclude `tmp/`, with dedicated passing tests. Historical tests were not weakened.

## Prepared future design, not executed

The B-only representation schema excludes U/R features, vulnerability identifiers, proof-of-vulnerability and security-test information. Three runtime conditions are configured: `NO_MEMORY`, `IRRELEVANT_CORRECT_MEMORY`, and `SOURCE_CORRECT_MEMORY`; all receive 16,384 post-ingestion trajectory tokens within a 32,768 physical context, 256 reserve, 4,096 per-turn maximum and 32 decisions. No-memory receives no junk padding and no conversation compaction is allowed. Compatibility remains limited to Qwen2.5-Coder-32B-Instruct and Devstral-Small-2507, neither of which was run.

The future seed mode remains deferred between `DETERMINISTIC_CANONICAL` and `STOCHASTIC_PAIRED` until excluded-task GPU qualification. Tasks, not seeds, remain the independent units. The p* ontology and memory packet format are frozen in the pivot artifacts, but no p* values, source corpus, source matcher or memory packet exists.

## Limitations and blockers

1. Wagtail B aborts at test collection, so it fails the strict task matrix and is permanently development-only.
2. SusVibes task statements are generated from the mask, not independently authored, and can state safety-relevant expected behavior.
3. The security evaluator is focal and incremental, not a global security assessment.
4. Derived SIF bytes are not deterministic; manifest digests and extracted tree hashes are the locks.
5. Cost/storage estimates use only five heterogeneous cases.
6. The source corpus and source matcher are deliberately absent.
7. Unseen screening, GPU qualification and study execution remain unauthorized.

## Decision boundary

The evidence supports only this claim: SusVibes can supply a reproducibly screenable B/U/R target substrate with independent task and focal-security executions. It does not show that any source memory exists, that p* can be assigned, that memory changes unsafe completion, that historical developers reused a procedure, or that uptake/mediation occurs.

Generated at 2026-09-02T08:05:22.829562+00:00 from model-free development evidence.
