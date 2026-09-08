# SecureVibeBench + ARVO seen-set development report

## Decision

The pipeline is **not ready** for prospective confirmatory screening. No unseen implementation, diff, description, or history was inspected. No evaluated coding model or GPU was run.

## Preserved discovery history

- Original protocol commit: `652ee155485afff55e045cf07e3958681f33f480`
- Original protocol SHA-256: `bab30dec3e90b91cf4122536640faaffb74dc40fadb364772371b5b3035474c3`
- Original final discovery commit and this branch base: `31cafe2cf794a3b737f491b9fd0a35e827de3db1`
- The prior ledger, screened positions, rejection evidence, protocol, and frozen results were not edited.

## What the data model actually means

SecureVibeBench derives B/PVIC as the first parent of the HF `vic` field and starts agents there. U is the historical VIC. ARVO-Meta supplies R through `fix_commit`. SecureVibeBench's “gold reference” is not R and is not a patch column: it is functional output obtained after the unfiltered per-ID script checks out U in a fresh vulnerable image. ARVO patch files encode the later R/VFC fix.

All eight mappings resolve, every U has exactly B as its single first parent, every U is an ancestor of R, and no seen mapping requires merge disambiguation. Exact trees and patch hashes are in `bur-security-matrices.json`.

## Execution findings

Five IDs were fully attempted in the strict functional matrix. Zero met B=FAIL, no-op=FAIL, irrelevant=FAIL, U=PASS, R=PASS. IDs 48736, 11060, 11074, and 48883 pass B under the stock comparator. ID 21916 distinguishes B from U, but R fails feature retention and its ARVO rebuild fails. Therefore the stock functional oracle cannot establish the required pre-feature B gate.

The official PoV was not modified. Three attempted IDs produced the conceptual B-absent/U-present/R-absent pattern (48736, 11060, 11074). jsoncpp R and all nDPI states had build failures, which remain infrastructure classifications rather than security failures.

## Containers

Pinned Docker images can be pulled and converted without root. Native Singularity execution is broken by host configuration, but an extracted SIF can be run equivalently in a rootless user namespace/chroot. The method needs a local temporary rootfs, resolver binding, and narrow APT/tar accommodations. No GPU is needed.

## Source procedure and memory

All six unique seen transformations were searched strictly before B with follow, move/copy blame, pickaxe, regex, and deterministic same-repository diagnostics. Fourteen same-file historical candidates were found, but none has machine-generated proof of correctness, safety, and a concrete p*. Move/copy blame and pickaxe also time out on large histories under a predeclared 10-second per-command budget. No source was selected, no memory was instantiated, and no similarity threshold was frozen.

## Feasibility claims

| Claim | Result |
|---|---|
| Historical pre-requirement B | PASS |
| Historical unsafe U | PARTIAL |
| Secure R | PARTIAL |
| Executable functionality | PASS |
| Executable PoV security | PARTIAL |
| B-negative task completion | FAIL |
| Mechanically retrievable source S | FAIL |

## Verification

The in-scope SecureVibeBench test module passes 17/17. A repository-wide `pytest` run was stopped after 438.57 seconds with 88 passed and 13 failures because unrelated batch-observer processes blocked on shared-filesystem I/O. The frozen AIM package hash failure reproduces unchanged in the original clean worktree at `31cafe2cf794a3b737f491b9fd0a35e827de3db1`; it was not repaired. `git diff --check` passes.

## Recommendation

Do not freeze or execute a confirmatory protocol. First obtain or predeclare an independent task-specific B-negative oracle and a source-correctness/safety validation mechanism on a new seen-only calibration set; then rerun all eight development cases before touching the 97-ID unseen universe.
