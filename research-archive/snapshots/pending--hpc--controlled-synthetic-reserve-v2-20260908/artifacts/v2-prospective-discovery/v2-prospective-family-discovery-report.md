# V2 Prospective Family Discovery Report

## Authoritative result

The prospective discovery protocol was frozen before screening, but the primary cohort is **not ready**. Tier 1 was exhausted with 0/8 candidates eligible. Screening then stopped before Tier 2 candidate 9 because the frozen protocol contains a genuine implementation ambiguity for the Tier 2 witness-presence gate. No eligibility criterion was relaxed or added after candidate outcomes were observed.

- `FINAL_ELIGIBLE = 0/4`
- `PRIMARY_COHORT_FROZEN = FALSE`
- `GPU_QUALIFICATION_READY = FALSE`
- `STUDY_RUN_AUTHORIZED = FALSE`

No evaluated-model inference and no GPU job occurred.

## Repository and chronology

The discovery worktree was created at `/home/s224049759/projects/correct-memory-study-worktrees/v2-prospective-family-discovery` on branch `feat/v2-prospective-family-discovery`, based on the exact final methodology-repair commit `ba1d0eed7313af4e19ea29b40f404d12960316a5`. That base contains the final V2 methodology-repair report and readiness artifacts.

The protocol was committed as `652ee155485afff55e045cf07e3958681f33f480` before candidate materialization or screening. Its authoritative JSON SHA-256 is `bab30dec3e90b91cf4122536640faaffb74dc40fadb364772371b5b3035474c3`. The candidate universe was subsequently frozen in commit `2bb92162def3142c976bd4c85d578dda759d9833`. Tier 1 lineage and task screening were committed in `e365d98a94552d1dccbe7c03d95b8bd7b4b596f7`, and Tier 1 source retrieval and semantic evidence were committed in `aecc736aa01fb2b72845a93af1195dab04b893be`.

The frozen source versions were:

| Source | Commit | Root tree | Role |
|---|---|---|---|
| VCC-Eval | `095cfcb18a588063342b1d53f98802b99545aba6` | `7dd599b6614c938ace220b112c003c3dba1ffe2d` | introduction/fix provenance |
| Vul4J | `376411da11fa705019f731404de1d0679fe73537` | `7e093c58eca028ad6c61994db194145bb22567a1` | reproducible vulnerabilities and witnesses |
| VulnLoc | `e1f607abea71db0eb57b41684f3dfae0ecee4321` | `d007c46d6807cd380a33c1b3c2e3e002d9fbcdb8` | Tier 4 fallback |
| SecBench.js | `5d362353550a8baa42bba34edd26e5fb86d41b60` | `ed1236e235c5fc1eee45a359cecd6272b76c64fb` | Tier 4 fallback |

## Frozen candidate universe

The deterministic materializer produced 947 ordered candidates. The initial registration ledger occupies 963,753 bytes and has SHA-256 `76dce21327e3a5ad751991d46c686f0408893b0d52a087f00ee099455e869864`. Later evidence was appended without changing that prefix.

| Tier | Candidates | Screened | Status |
|---|---:|---:|---|
| VCC-Eval ∩ Vul4J | 8 | 8 | exhausted; no eligible candidate |
| Remaining VCC-Eval with upstream-witness gate | 180 | 0 | halted before position 9 |
| Remaining Vul4J with independent exact-INTRO gate | 121 | 0 | not reached |
| VulnLoc | 39 | 0 | not reached |
| SecBench.js | 599 | 0 | not reached |

The universe size is not the screening denominator. The exact screening denominator is eight.

## Tier 1 results

| Position | CVE | B | INTRO/U | FIX/R | Result |
|---:|---|---|---|---|---|
| 1 | CVE-2014-0116 | `ba1850a1382765eb51c58103a8c5ee7c0d9417f4` | `bfbc4c04e007393986f374a02dfb7ded23bc9a05` | `74e26830d2849a84729b33497f729e0f033dc147` | historical unsafe procedure already existed in B |
| 2 | CVE-2018-11771 | `8301ee7fec23ffdee9ea2c8ce5a8b80f343744e5` | `29f975ea99d9b9310c6fc33ac4f844fb10f4d98a` | `a41ce6892cb0590b2e658704434ac0dbcb6834c8` | task not behaviorally identifiable |
| 3 | CVE-2018-1324 | `86148ca23eb9caa0ac16b270b1a444230dfef2a9` | `a433f625f89c1d464b05186411ff20802e292fb4` | `2a2f1dc48e22a34ddb72321a4db211da91aa933b` | no all-YES source-safe analogue |
| 4 | CVE-2018-17202 | `cb1f096543f1294821c194173150be526d640ebf` | `c659a6007b258f3e2afc57cf2b4c4c5eb03fce74` | `6a79d35d6654d895d0a4b73b3a9282ec9aaeeb06` | no all-YES source-safe analogue |
| 5 | CVE-2018-18389 | `1b74de13fa49bba04fee9056de456fe936f4dee0` | `26ff65ccf13111c42942d8652e9e616e91e1fd08` | `46de5d01ae2741ffe04c36270fc62c6d490f65c9` | no all-YES source-safe analogue |
| 6 | CVE-2018-20157 | `0fa99d21cab6edf83360182fcf46cb4153e22c83` | `78edff6f7f410bb53c03e67f7f90a6d3521cee7f` | `6a0d7d56e4ffb420316ce7849fde881344fbf881` | no all-YES source-safe analogue |
| 7 | CVE-2019-0225 | `53f77a24d56d4e6b2cccdb82fed0958375867c55` | `5da3fd1da735f32b138a850d990a6f51190cef5f` | `88d89d6523802c044cfcb7930cba40d8eeb21da2` | task not behaviorally identifiable |
| 8 | CVE-2019-11272 | unavailable | `db12a50a32cd779e4f36f52dc2374692477bf94d` | `b2d4fec3617c497c5a8eb9c7e5270e0c7db293ee` | introducing commit object missing |

Five candidates had unanimous YES answers to task questions T1–T8. Position 1 nevertheless failed the separate historical-unsafe-implementation gate because the vulnerable procedure was already present in B. Positions 3–6 advanced to source retrieval. The frozen similarity engine returned respectively 1, 174, 284, and 8,001 occurrences. Every occurrence was retained and evaluated with the fixed Q1–Q12 form; none received all YES answers. Thus no source-safe memory, security witness execution, or five-state control matrix was constructed. This follows the cost-minimizing gate order: an objectively decisive earlier failure prevents expensive build and PoV work.

The rejection totals are:

- 4 × `REJECT_NO_ALL_YES_SOURCE_SAFE_ANALOGUE`
- 2 × `REJECT_TASK_NON_IDENTIFIABLE`
- 1 × `REJECT_HISTORICAL_UNSAFE_IMPLEMENTATION_NOT_INTRODUCED`
- 1 × `REJECT_A1_COMMIT_OBJECT_MISSING`

## Mandated halt before Tier 2

Tier 2 is defined as remaining VCC-Eval candidates for which the upstream repository contains an existing reproducible security regression test or exploit. The frozen protocol defines the desired property and the A5/A6 execution outcomes, but it does not define a bounded deterministic discovery procedure for finding such an artifact or an evidentiary rule for declaring it absent.

This becomes material at position 9. Looking only at files changed by the fixing commit would be fast, but absence from that patch does not prove absence elsewhere in repository history, linked historical metadata, or upstream test assets. Adopting that shortcut now would create a new false-negative-prone eligibility rule after protocol freeze. Expanding the search ad hoc until a researcher feels satisfied would violate deterministic ordering and constrained selection.

The protocol explicitly sets `stop_rule.implementation_ambiguity` to `STOP_AND_DOCUMENT`. Screening therefore stopped before opening Tier 2 candidate outcomes. Candidate 9 and all later candidates remain `NOT_SCREENED` in the append-only ledger. This is a protocol implementation blocker, not a rejection of those candidates and not exhaustion of the frozen fallback tiers.

## Verification and reproducibility

The discovery-specific suite passed: `10 passed in 0.13s`. JSON syntax, ledger-prefix integrity, and whitespace checks also pass.

The configured repository-wide pytest run was attempted. It reached 230 passes and 13 failures before being interrupted after 523.82 seconds when an out-of-scope Devstral environment-verification subprocess was blocked in filesystem I/O. The observed failures concern existing frozen-family hashes, backend registration, batch-attestation subprocess timeouts, and calculator finalization; none is in `tests/test_v2_prospective_discovery.py`. No evaluated model was invoked, no GPU job was launched, and no completed raw experimental output was edited.

All screened evidence is committed under `screening-evidence/`, and all source dataset revisions, metadata hashes, candidate registrations, decisions, and evidence hashes are recorded. Because no family is eligible, the control, memory, witness, and per-family reproducibility indexes are intentionally empty.

## Readiness conclusion

`V2_PROSPECTIVE_CONFIRMATORY_COHORT_V1` cannot be frozen. GPU qualification is not ready, and a study run remains unauthorized. The scientifically valid next action is to write and commit a successor prospective protocol—without modifying v1—that freezes a bounded Tier 2 witness-discovery and absence rule before any Tier 2 candidate outcome is opened.
