# Research Git archive — 8 September 2026

Repository: [anjum613/correct-memory-study](https://github.com/anjum613/correct-memory-study).

GlobalProtect was connected, and Fedora, the Deakin HPC, and the workstation were inspected. The archive preserves 561 existing commits (including saved-stash history): 9 authored in July, 383 in August, and 169 in September 2026. Existing author dates, committer dates, identities, and Git objects were preserved. New snapshots use the actual date of capture; file modification times are recorded as provenance, not asserted as historical commit dates.

Readable histories use `archive/hpc/`, `archive/fedora-N/`, and `archive/workstation/` branches. Pending work uses `archive/pending/`. Differing versions were kept separately. Readable versions are additionally collected in separate folders on `main`, using a history-preserving archival merge. Differing experiment implementations have not been combined into a single codebase.

Original histories containing unresolved credential-like values from third-party research captures, oversized capture files, and explicitly encrypted-only snapshots are preserved inside an authenticated encrypted Git bundle. Download the parts, manifest, and recovery script from the [research archive release](https://github.com/anjum613/correct-memory-study/releases/tag/research-archive-20260908).

**Recovery key:** `/home/anjum/.local/share/research-git-archive-20260908.key`. This key stays on Fedora and is not uploaded. Save a separate secure copy: the encrypted archive cannot be recovered without it.

## Scope and exclusions

Standalone snapshots include the three Fedora manuscript versions, selected research scripts and audit folders, HPC experiment plans, run evidence and Slurm logs, and workstation environment/protocol/smoke evidence. The two workstation repositories had clean working trees.

Generated caches, virtual environments, nested repository working copies, runtime directories, and model/container caches were not indiscriminately added. Existing repositories' ignore rules were respected. The standalone HPC transfer excluded model weights, private configuration files, cache directories, and files at least 50 MiB; a follow-up scan found two oversized container/runtime artifacts, recorded in `hpc-external-large-files.json`. This is a research archive, not a complete machine or environment backup.

Credential-bearing and oversized Fedora research captures omitted from readable snapshots are preserved on the encrypted-only evidence branch inside the bundle. Exclusion manifests record each source path and reason. Original working files, staging areas, and active branches remain available on their source machines; new snapshots were made with separate Git indexes.

## Dates and GitHub's contribution graph

The upload and release activity happened on 8 September. Original commits retain their historical dates. Readable source histories were merged into `main` as original commit parents, so their historical dates remain intact. Encrypted-only histories remain inside the recovery bundle and are not exposed as public Git objects. GitHub requires eligible commits on the default or `gh-pages` branch, with an email associated with the account. See [GitHub's contribution documentation](https://docs.github.com/en/account-and-profile/how-tos/contribution-settings/troubleshooting-missing-contributions).

GitHub blocks normal Git files over 100 MiB; see [GitHub's size documentation](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github). Oversized originals are therefore held in the encrypted bundle, which is split into release assets.

## Captured working copies

| Machine | Source | Files in snapshot | Excluded entries |
| --- | --- | ---: | ---: |
| fedora | `/home/anjum/Documents/research/correct-memory-study-worktrees/candidate-screening-v020-hybrid` | 224120 | 48 |
| fedora | `/home/anjum/hpc-smoke3.u34YsZ` | 10 | 0 |
| fedora | `/home/anjum/candidate-discovery-audit-20260814T123116Z` | 115611 | 20 |
| fedora | `/home/anjum/candidate-discovery-canary-20260816` | 344033 | 84 |
| fedora | `/home/anjum/correct-memory-study-controlled-v2` | 245 | 0 |
| fedora | `/home/anjum/controlled-synthetic-v3-construction` | 33 | 0 |
| fedora | `/home/anjum/candidate-discovery-canary-20260816/.worktrees/live-verification-v015-safe-20260820` | 19 | 0 |
| fedora | `/home/anjum/candidate-discovery-canary-20260816/.worktrees/prospective-screening-protocol-v01` | 224215 | 7 |
| hpc | `/home/s224049759/projects/correct-memory-study-worktrees/controlled-synthetic-continuation` | 1326 | 370 |
| hpc | `/home/s224049759/projects/correct-memory-study-worktrees/controlled-synthetic-final` | 12 | 0 |
| hpc | `/home/s224049759/projects/correct-memory-study-worktrees/controlled-synthetic-reserve-v2` | 46 | 0 |
| hpc | `/home/s224049759/projects/correct-memory-study-worktrees/controlled-synthetic-v2` | 881 | 370 |
| hpc | `/home/s224049759/projects/correct-memory-study-worktrees/controlled-synthetic-vx` | 4197 | 349 |
| hpc | `/home/s224049759/projects/correct-memory-study-worktrees/qwen3-runpod-final-13` | 13 | 0 |
| hpc | `/home/s224049759/projects/correct-memory-study-worktrees/track-b-httpx-v01` | 34 | 0 |
| hpc | `/home/s224049759/projects/correct-memory-study-worktrees/track-b-mcp-pinot-v01` | 9 | 0 |
| hpc | `/home/s224049759/projects/correct-memory-study` | 859 | 79 |
| hpc | `/home/s224049759/projects/worktrees/benchmark-selection-v1` | 115611 | 20 |
| fedora | `/home/anjum/output/research-git-audit/fedora-loose` | 49438 | 65487 |
| workstation | `/home/anjum/output/research-git-audit/workstation-loose` | 40 | 1 |
| hpc | `/home/anjum/output/research-git-audit/hpc-loose` | 292447 | 92 |

Counts are file entries across independent snapshots and include duplicates shared between working copies. Full refs and source mappings are in `audit-summary.json`. Per-file SHA-256 hashes and modification times are in each snapshot’s `.research-archive/` manifest.
