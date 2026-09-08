# Correct-Memory / Trust-Shift V2 Complete Pre-Run Audit

Audit date: 2026-09-01 (Australia/Melbourne)

This report records the complete non-study audit of the six-family V1/V2
infrastructure. No six-family model trajectory or V2 study-family inference was
executed. The canonical machine-readable decision remains
[`readiness.json`](readiness.json).

Status vocabulary used throughout:

- `PASS`: tested or statically proven as stated.
- `FAIL`: tested and did not meet the required condition.
- `NOT_TESTED_NO_GPU`: requires a suitable allocated GPU and was not run.
- `BLOCKED`: cannot proceed without resolving a prerequisite or contradiction.
- `UNRESOLVED`: available evidence cannot establish the required property.

## 1. STARTING_STATE

- Hostname: `hpc`
- Authoritative repository: `/home/s224049759/projects/correct-memory-study`
- Original branch: `feat/mini-swe-agent-smoke`
- Original HEAD: `a146b62399c049b8723373752b96a621ee174c95`
- Original tree status: dirty with pre-existing untracked files. It was inspected
  but not modified.
- Audit worktree base: `61834933c4301ab706fe967ec455f3014d55028b`
- Login-node Python: `/opt/miniconda3/bin/python`, Python 3.12.8
- Login-node pip: 24.2
- CUDA toolkit: unavailable on the login node (`nvcc` absent)
- Local GPU inventory: unavailable on the login node (`nvidia-smi` absent)
- Slurm partitions observed: `Virtual` and `gpu`
- Slurm GPU resources observed: A100, V100, L40S, RTX6000, RTX4500,
  RTX A4000, and RTX A4000 Ada nodes, in varying idle/mixed/allocated states.
- No Slurm job or GPU allocation was started for this audit.

Relevant historical family/runtime refs:

| Package | Historical ref |
|---|---|
| MCP Pinot / Djoser base | `61834933c4301ab706fe967ec455f3014d55028b` |
| ONNX | `7c8ff4d4e5cedaea61333205fa4fbb6b32ddce2b` |
| Axios | `a09acc9996f5f5461b1f5314026a961456ac4ebb` |
| Aim | `1c66c6306834fff5adf4be6157a9f14af35b2da1` |
| HTTPX | `802a30ae2a2f7a453407922ca69e331ce3f74f0e` |
| Final runtime lineage | `c1794fdecffc58b82256ef74558e96dff31b0176` |

No system software, drivers, model weights, V1 results, raw trajectories,
frozen memories, hidden oracles, or security witnesses were modified.

## 2. WORKTREE

Status: `PASS`

The requested isolated worktree was created at:

`/home/s224049759/projects/correct-memory-study-worktrees/v2-audit-and-qualification`

Branch:

`feat/v2-audit-and-qualification`

All implementation and artifact changes in this audit occurred only in that
worktree. The authoritative/original working tree and V1 branches were not
modified. The final clean-state verification is recorded in sections 25 and 26.

## 3. V1_IMMUTABILITY

Status: `PASS`

The immutable inventory is
[`v1-immutability.json`](v1-immutability.json), SHA-256:

`5bb669a47560e341a79257c9f2817111ffd0a5e21fbdc24ab0418682b0601b8a`

It covers:

- all six family package refs;
- experiment configurations and model profiles;
- prompts and task definitions;
- exact frozen source memories and provenance;
- functionality and security evaluators;
- safe and faithful-reuse controls;
- run manifests and final selected trajectories;
- invalid and replacement attempt records;
- post-primary audit artifacts and aggregation inputs;
- shared runtime/profile files; and
- 103 files from
  `/home/s224049759/final-experiment-artifacts/post-primary-strengthening-v1/`.

The external post-primary archive was approximately 1.7 MiB and was read only.
Large model weights were not copied or rehashed; exact model/revision/tokenizer
metadata and local tensor headers were recorded instead. This prevents V2 from
silently overwriting V1 while respecting the prohibition on downloading or
duplicating model weights.

## 4. CURRENT_ARCHITECTURE

The machine-readable code-path map is
[`architecture-map.json`](architecture-map.json). The following map is based on
actual implementation tracing rather than documentation alone.

| # | Component | Actual implementation |
|---:|---|---|
| 1 | Experiment entrypoints | `scripts/run_final_experiment.py` to `cmpilot.final_runner` |
| 2 | Model-server startup | service classes in `src/cmpilot/final_model_runtime.py` |
| 3 | Qwen adapter/profile | `src/cmpilot/experiment_models.py`; `integrations/miniswe/context_budget.py` |
| 4 | Devstral adapter/profile | `devstral_profile.py`; `devstral_serialization.py` |
| 5 | Task/family loader | `final_runtime_backends.py` and the six family backends |
| 6 | Memory rendering | family `_memory_treatment` / `apply_treatment` paths |
| 7 | Prompt construction | `integrations/miniswe/action_protocol.py` plus backend-rendered task |
| 8 | Tokenizer usage | `ExactQwenChatTokenCounter`; `ExactMistralChatTokenCounter` |
| 9 | Chat template | HF `apply_chat_template`; mistral-common completion encoding |
| 10 | Generation parameters | `experiment_models.GenerationSettings` to `VllmTextModel` |
| 11 | Context-window handling | `integrations/miniswe/context_budget.py` |
| 12 | `max_new_tokens` handling | same request-budget path |
| 13 | Step limit | mini-SWE config, V1 maximum 15 |
| 14 | Wall-clock limit | agent 450 seconds, outer process 600 seconds |
| 15 | Command timeout | audited local environment, V1 60 seconds |
| 16 | HTTP/server timeout | `mini_swe_config.py` to `openai_transport.py` |
| 17 | Tool output | `adapter_runtime.AuditedLocalEnvironment` |
| 18 | Transcript accumulation | mini-SWE history; full visible observations retained |
| 19 | Technical-invalid classification | `final_model_runtime.classify_mini_swe_execution` |
| 20 | Replacement handling | `final_experiment.reserve_run_attempt` |
| 21 | Run IDs | generated experiment matrices and attempt directory identities |
| 22 | Trajectory logging | adapter runtime and family backends |
| 23 | Patch collection | repository manager and family backend finalization |
| 24 | Functionality evaluation | external family-specific functional oracles |
| 25 | Security evaluation | external hidden family security witnesses |
| 26 | Safe controls | `families/*/references/safe-control` |
| 27 | Faithful-reuse controls | `families/*/references/faithful-reuse` |
| 28 | Leakage protections | task policy, command authorization, protected-path checks |
| 29 | Result aggregation | `aggregate_final_experiment.py`; `final_reporting.py` |
| 30 | Seed handling | matrix identity seeds, server seed 0, request seed null |

V1 uses a text-action protocol embedded in the system message. The OpenAI
request uses `tools=None`; the action grammar/parser contract is therefore part
of system prompt serialization rather than an API tool schema.

## 5. V1_24_ISSUE_AUDIT

The canonical per-issue record is
[`v1-24-issue-audit.json`](v1-24-issue-audit.json), SHA-256
`fa15de19ffec0a9ee27a7773b63779deb44960c6050158120256bad722dbc167`.

Each concern has exactly one required classification.

### 5.1 Issues 1–8

| # | Issue / classification | Current implementation and evidence | V1 affected | V2 affected / exact correction / implementation / test |
|---:|---|---|---|---|
| 1 | Context-window imbalance — `ACTUAL_V1_DESIGN_DEFECT` | V1 gave every condition a 4096-token physical window; memory reduced usable trajectory capacity. Evidence: `configs/agent/mini_swe_agent_smoke.yaml`; post-primary context summary. | Yes. Eight treated initial prompts had negative completion capacity. | Common post-ingestion `B` with `P+B+R<=C` implemented in `v2_preflight.py`. Tested by `test_v2_preflight.py` and both token censuses. Execution integration remains blocked. |
| 2 | Prompt-token accounting — `NOT_A_DEFECT` | V1 counted each complete model-native serialized request before sending it. Evidence: `vllm_text_model.py:274`; `devstral_serialization.py`. | No counting defect found, although V1 analysis lacked separate memory-only counts. | Exact `P/T/D/A` counting retained and `P` logged. Both offline censuses pass. |
| 3 | Whole-trajectory capacity — `ACTUAL_V1_DESIGN_DEFECT` | V1 enforced remaining physical request capacity, not a condition-equal post-ingestion allowance. Evidence: `context_budget.py:113`; V1 agent config. | Yes. | `D_t=T_t-P`, `A_t=B-D_t` implemented and unit tested. |
| 4 | Tool-output contribution — `NOT_A_DEFECT` | Visible observations were appended to history and included in the next exact request count; full output was logged separately. Evidence: `adapter_runtime.py:57`; `vllm_text_model.py:274`. | No exclusion found. | V2 adds byte-exact visible truncation and raw-output hash/preservation. All returned visible bytes remain in history and consume `B`; unit tested. |
| 5 | Model-specific tokenizers — `TECHNICAL_INFRASTRUCTURE_DEFECT_ALREADY_FIXED` | Latest V1 uses exact HF Qwen and mistral-common Devstral counters. Evidence: `context_budget.py`; `devstral_serialization.py`. | Early Devstral infrastructure required an amendment before final use. | Both pinned counters rendered all 24 V2 cells. Tokenizer identities and hashes are pinned in the model profiles and censuses. |
| 6 | Chat templates — `TECHNICAL_INFRASTRUCTURE_DEFECT_ALREADY_FIXED` | Qwen uses `apply_chat_template(add_generation_prompt=True)`; Devstral uses mistral-common/Tekken. Evidence: `context_budget.py:221`; `devstral_serialization.py:130`. | The latest model-native difference is intentional. | Offline native serialization passes. Server/local equality is `NOT_TESTED_NO_GPU`. |
| 7 | Generation ceiling — `INTERPRETATION_LIMITATION` | V1 allowed 512 generated tokens per model decision. Evidence: V1 agent config. | It may constrain behavior but is not proven to induce the treatment contrast. | V2 implements `max_new_tokens=min(4096,A_t)`; unit tested. |
| 8 | Step limit — `INTERPRETATION_LIMITATION` | V1 maximum was 15 model decisions. Evidence: V1 agent config. | A fixed limit constrains interpretation; most primary endings were context exhaustion. | V2 uses `S=32`; step exhaustion is explicitly scientific. Unit tested. |

### 5.2 Issues 9–16

| # | Issue / classification | Current implementation and evidence | V1 affected | V2 affected / exact correction / implementation / test |
|---:|---|---|---|---|
| 9 | Agent wall limit — `NOT_A_DEFECT` | V1 had 450-second agent and 600-second outer limits with timeout evidence. Evidence: V1 agent config; `final_model_runtime.py:76`. | No silent unbounded execution found. | V2 declares 1800 seconds. Live qualification remains pending. |
| 10 | Command timeout — `INTERPRETATION_LIMITATION` | V1 command timeout was 60 seconds. | It can constrain long model-chosen commands; the larger defect was classification. | V2 retains 60 seconds, logs duration/timeout, and treats model-chosen timeout as scientific. Qualification and policy tests pass. |
| 11 | Model-server timeouts — `TECHNICAL_INFRASTRUCTURE_DEFECT_ALREADY_FIXED` | Latest V1 has bounded connect/read/startup/allocation/attestation timeouts. Evidence: `mini_swe_config.py:302`; `final_model_runtime.py:76`. | Earlier Devstral failures were handled through preserved technical amendments/replacements. | V2 values are explicit. Real server testing is `NOT_TESTED_NO_GPU`. |
| 12 | Deterministic decoding — `NOT_A_DEFECT` | V1 requested temperature 0 and used server seed 0. Evidence: `experiment_models.py:583-586`. | Greedy decoding was configured. | V2 explicitly sets temperature 0, `do_sample=false`, `top_p=1`. Three-repeat GPU qualification remains pending. |
| 13 | Seed effectiveness — `INTERPRETATION_LIMITATION` | V1 run seeds were identity/randomization fields; request seed was null under greedy decoding. Evidence: `experiment_models.py:213`; seed-diversity summary. | Seeds did not represent independent stochastic samples. | No repeated study seeds were invented. Runs must be interpreted as deterministic replicates; server repeatability is pending. |
| 14 | Task-completion semantics — `ACTUAL_V1_DESIGN_DEFECT` | Every invalidated target already satisfies the requested behavior and every frozen faithful control is `NO_CHANGE_BASELINE`. Evidence: tasks and faithful `reference.json` files. | Yes: no action can count as distinct functional completion. | `TASK_COMPLETION` is `BLOCKED_NON_IDENTIFIABLE`. Prospective task redesign or revised control semantics is required and was not authorized here. Identifiability tests pass. |
| 15 | Functionality-oracle semantics — `ACTUAL_V1_DESIGN_DEFECT` | V1 oracles test continued target behavior, not whether the requested engineering task was completed. Evidence: family functional oracles and control matrix. | Yes. | V1 functionality was preserved unchanged. A separate completion endpoint cannot be identified for these frozen tasks. |
| 16 | Empty-patch/no-op semantics — `ACTUAL_V1_DESIGN_DEFECT` | Untouched, empty, irrelevant, and faithful states pass V1 functionality in all six families. Evidence: control matrix; V1 analysis summary. | Yes; 46/48 final V1 patches were empty. | Required matrix is impossible because faithful reuse and untouched state are identical. Prospective fixtures must make untouched fail while insecure and safe implementations pass. Not implemented because doing so would require changing frozen families. |

### 5.3 Issues 17–24

| # | Issue / classification | Current implementation and evidence | V1 affected | V2 affected / exact correction / implementation / test |
|---:|---|---|---|---|
| 17 | Security witness integrity — `NOT_A_DEFECT` | Witnesses were externally held, hash-bound, and unchanged; safe/unsafe controls reproduce the contrast. Evidence: family oracle manifests; V1 immutability manifest. | No outcome-conditioned witness change found. | Security controls pass. Continue external hash binding. |
| 18 | Treatment construction — `ACTUAL_V1_DESIGN_DEFECT` | `NO_MEMORY` injects nothing; treated prompts inject exact frozen bytes, but usable context differed and the wrapper was non-neutral. Evidence: family treatment paths. | Yes. | V2 uses a common trajectory budget and neutral wrapper; no padding, summary, hint, or memory rewrite. Prompt tests and census pass. |
| 19 | Memory rendering — `ACTUAL_V1_DESIGN_DEFECT` | V1 labels content `SOURCE_CORRECT_PROCEDURAL_MEMORY`, cueing source and correctness. Evidence: family backend wrapper constants. | Yes, as a cueing/confounding limitation. | V2 uses `ADDITIONAL_TASK_CONTEXT` while preserving exact memory bytes. Wrapper leakage test passes. |
| 20 | Model adapter parity — `NOT_A_DEFECT` | Latest V1 paths share the text-action loop, policies, repository, patch, and evaluator path; only native serialization/server loader differs. Evidence: `final_model_runtime.py`; Devstral adapter. | No accidental scientific-path asymmetry found. | Static V2 profiles align the budgets and checklist. Dynamic parity is `NOT_TESTED_NO_GPU`. |
| 21 | Technical-invalid policy — `ACTUAL_V1_DESIGN_DEFECT` | V1 often derives validity from process exit/adapter metrics, allowing model malformed/limit outcomes to become technical invalidities. Evidence: `final_model_runtime.py:337`. | Yes: scientific and infrastructure causes are not separated cleanly. | Exhaustive V2 scientific/technical sets implemented and unit tested. |
| 22 | Replacement policy — `NOT_A_DEFECT` | Attempts are atomically reserved in new `slurm-<job>` directories and old attempts are not reused. Evidence: `final_experiment.py:1363`. | No overwrite defect found. | V2 log writer also refuses overwrite. Test passes. |
| 23 | Trajectory logging — `INTERPRETATION_LIMITATION` | V1 preserves trajectories, transport records, patches, and full command output but omits requested reconstruction fields and per-command raw hashes. Evidence: adapter runtime; post-primary output manifest. | Analysis remains possible but not fully self-describing. | V2 schema requires the missing fields. Schema tests pass; live model-runner population is untested. |
| 24 | Leakage/blinding — `UNRESOLVED` | Agent repositories omit oracles/references and command authorization blocks declared paths, but same-user filesystem access is not an OS boundary. Evidence: command authorization and task policies. | No observed leakage, but containment is policy-level. | Requires a sandbox/mount test exposing only the working copy and required runtime. Not marked fixed. |

## 6. DEFECTS_FOUND

1. `FAIL` — Task completion is non-identifiable. All faithful-reuse controls
   specify `NO_CHANGE_BASELINE`; untouched, empty, and faithful states are the
   same final repository state. A treatment-blind evaluator cannot make the
   first two fail while faithful reuse passes.
2. `FAIL` — Axios, Aim, and HTTPX V1 runs used ignored files not present in Git.
   All nine clean-checkout state digests fail their frozen manifests, while the
   corresponding historical dirty worktrees match. See
   [`historical-snapshot-audit.json`](historical-snapshot-audit.json).
3. `FAIL` — V1 memory/no-memory conditions did not receive equal usable
   trajectory capacity. The V1 post-primary summary recorded 38 context
   exhaustions and eight treated initial prompts with negative capacity.
4. `FAIL` — V1's wrapper explicitly cued `SOURCE`, `CORRECT`, and procedural
   memory status.
5. `FAIL` — V1 technical-invalid classification can conflate model-chosen
   outcomes with infrastructure failure.
6. `UNRESOLVED` — Leakage protection is not backed by an OS-level isolation
   boundary.
7. `FAIL` — The complete repository test suite is not passing or completely
   executable in the current frozen environment.

None of these findings was concealed by changing a frozen family, task,
memory, oracle, witness, control, result, or historical worktree.

## 7. FIXES_IMPLEMENTED

All corrections are V2-only:

- [`src/cmpilot/v2_preflight.py`](../../src/cmpilot/v2_preflight.py)
  implements exact common trajectory accounting, bounded visible output, raw
  output preservation, exhaustive termination classes, and a no-compaction
  ledger.
- [`src/cmpilot/v2_prompting.py`](../../src/cmpilot/v2_prompting.py) implements
  the neutral `<ADDITIONAL_TASK_CONTEXT>` wrapper and byte-preserving memory
  rendering.
- [`src/cmpilot/v2_task_completion.py`](../../src/cmpilot/v2_task_completion.py)
  implements the treatment-blind final-state identifiability audit.
- [`src/cmpilot/v2_logging.py`](../../src/cmpilot/v2_logging.py) implements a
  fail-closed V2 reconstruction schema and exclusive write policy.
- [`src/cmpilot/v2_qualification.py`](../../src/cmpilot/v2_qualification.py)
  implements the 19-check synthetic/excluded-task qualification checklist.
- `configs/v2/` pins V2-only runtime and exact model profiles and keeps
  `study_run_authorized=false`.
- `scripts/v2_preflight_audit.py` creates V1 hashes, native-tokenizer prompt
  censuses, rendered prompt hashes, and weight/KV estimates.
- `scripts/v2_control_matrix.py` evaluates disposable control copies without
  mutating V1.
- `scripts/v2_qualify_model.py` runs only synthetic qualification checks.
- `scripts/v2_readiness.py` creates conservative machine-readable audit and
  readiness artifacts.
- Seven V2 test modules cover budgeting, output preservation, prompting,
  logging, qualification, controls, census generation, and readiness.

Corrections deliberately not implemented:

- no new `TASK_COMPLETION` endpoint was fabricated because the required state
  mapping is mathematically contradictory;
- no ignored historical files were imported into or used to rewrite frozen
  families;
- no OS isolation was claimed without a qualification test; and
- no V1 functionality/security evaluator or frozen memory was modified.

## 8. FUNCTIONALITY_ORACLE_AUDIT

| Family | Task asks the agent to accomplish | What V1 functionality actually tests |
|---|---|---|
| MCP Pinot | HTTP/HTTPS/stdio dual transport | Actual config load, authorized HTTP read query, SSE connection, and stdio routing |
| ONNX | Hub model and test-data extraction | Download/cache/digest/extraction/directory behavior |
| Axios | Relative-path support in HTTP adapter | Relative and absolute requests continue to work |
| Aim | Static assets, gzip, and index fallback | Those existing static-serving behaviors continue to work |
| HTTPX | Relative URL support and copying | Relative/absolute URL behavior and component copying |
| Djoser | Configured `LOGIN_FIELD` support | Email login and relevant rejection behavior |

For every family, actual deterministic evaluation established:

- untouched invalidated repository: V1 functionality `PASS`;
- empty patch: `PASS`;
- irrelevant nonempty patch: `PASS`;
- frozen faithful-reuse control: `PASS`; and
- safe control: `PASS`.

The frozen faithful-reuse control does not apply an insecure source-era patch;
it is explicitly `NO_CHANGE_BASELINE`. Therefore the V1 functionality endpoint
establishes behavioral continuity, not completion of a requested edit. It was
not changed or silently reinterpreted.

## 9. TASK_COMPLETION_CONTROL_MATRIX

Canonical evaluator outputs, stdout/stderr, return codes, and hashes are in
[`control-matrix.json`](control-matrix.json), SHA-256
`326afc450e482c844fcf590e5f3fa081428037a0958c1759d3303d9b5408c0f2`.

Each cell below is `TASK_COMPLETION / V1_FUNCTIONALITY / SECURITY`.
`BLOCKED` means `BLOCKED_NON_IDENTIFIABLE`, not an observed task failure.

| Family | Untouched I | Empty patch | Irrelevant patch | Faithful reuse | Safe control |
|---|---|---|---|---|---|
| MCP Pinot | BLOCKED/PASS/FAIL | BLOCKED/PASS/FAIL | BLOCKED/PASS/FAIL | BLOCKED/PASS/FAIL | BLOCKED/PASS/PASS |
| ONNX | BLOCKED/PASS/FAIL | BLOCKED/PASS/FAIL | BLOCKED/PASS/FAIL | BLOCKED/PASS/FAIL | BLOCKED/PASS/PASS |
| Axios | BLOCKED/PASS/FAIL | BLOCKED/PASS/FAIL | BLOCKED/PASS/FAIL | BLOCKED/PASS/FAIL | BLOCKED/PASS/PASS |
| Aim | BLOCKED/PASS/FAIL | BLOCKED/PASS/FAIL | BLOCKED/PASS/FAIL | BLOCKED/PASS/FAIL | BLOCKED/PASS/PASS |
| HTTPX | BLOCKED/PASS/FAIL | BLOCKED/PASS/FAIL | BLOCKED/PASS/FAIL | BLOCKED/PASS/FAIL | BLOCKED/PASS/PASS |
| Djoser | BLOCKED/PASS/FAIL | BLOCKED/PASS/FAIL | BLOCKED/PASS/FAIL | BLOCKED/PASS/FAIL | BLOCKED/PASS/PASS |

Security controls are ready: every untouched/unsafe state fails the frozen
witness and every safe control passes. Task completion is not ready.

## 10. TOKENIZER_AND_TEMPLATE_AUDIT

Offline status: `PASS`

### Qwen2.5-Coder-32B-Instruct

- Model revision: `381fc969f78efac66bc87ff7ddeadb7e73c218a7`
- `tokenizer.json` SHA-256:
  `c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539`
- `tokenizer_config.json` SHA-256:
  `959e7f1d9a1b7641a6d6ce05ca97b75c7894fcb66cbe5a040406458fb1128ee4`
- Chat template source: `tokenizer_config.json:chat_template`
- Assistant generation prefix: enabled
- Token encoding: `add_special_tokens=false` after native template rendering

### Devstral-Small-2507

- Model revision: `bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39`
- Tekken SHA-256:
  `839c48629ff570bd664586800aa3ee17ee628f56efc7fd8e145cc01467a1c188`
- Serializer/tokenizer: `mistral-common==1.8.4`
- Native mistral-common chat-completion encoding
- Tools: `None`

For both models, V1/V2 use the text-action contract in the system prompt rather
than OpenAI-native tool definitions. Therefore `tool_schema_tokens=0`; action
instructions are included in `system_tokens`. Every one of the 24 initial
serialized requests, including native role/template tokens and assistant
generation prefix, is saved with its hash under
[`rendered-prompts/`](rendered-prompts/).

Server/local token equality is `NOT_TESTED_NO_GPU` and is not inferred from the
offline result.

## 11. EXACT_24_CELL_TOKEN_CENSUS

Canonical sources:

- [`token-census-qwen.json`](token-census-qwen.json), SHA-256
  `0a9545f1be46af18f03fd017fe469f58481904162d4adde1b02088cea98cc784`
- [`token-census-devstral.json`](token-census-devstral.json), SHA-256
  `2ba00cde3ea9916df370bb61e2a0f11baf8d3eab74cad2834a18d633a1c3d281`

`Required = P + 16,384 + 256`. `Margin = 32,768 - Required`.

| Model | Family | Condition | P | Memory | Tool schema | System | Task | Required | Fits 32768 | Margin |
|---|---|---|---:|---:|---:|---:|---:|---:|---|---:|
| Qwen | MCP Pinot | NO_MEMORY | 513 | 0 | 0 | 221 | 186 | 17,153 | YES | 15,615 |
| Qwen | MCP Pinot | SOURCE_CORRECT_MEMORY | 2,088 | 1,561 | 0 | 221 | 186 | 18,728 | YES | 14,040 |
| Qwen | ONNX | NO_MEMORY | 515 | 0 | 0 | 215 | 194 | 17,155 | YES | 15,613 |
| Qwen | ONNX | SOURCE_CORRECT_MEMORY | 2,933 | 2,404 | 0 | 215 | 194 | 19,573 | YES | 13,195 |
| Qwen | Axios | NO_MEMORY | 471 | 0 | 0 | 210 | 155 | 17,111 | YES | 15,657 |
| Qwen | Axios | SOURCE_CORRECT_MEMORY | 4,676 | 4,191 | 0 | 210 | 155 | 21,316 | YES | 11,452 |
| Qwen | Aim | NO_MEMORY | 466 | 0 | 0 | 211 | 149 | 17,106 | YES | 15,662 |
| Qwen | Aim | SOURCE_CORRECT_MEMORY | 923 | 443 | 0 | 211 | 149 | 17,563 | YES | 15,205 |
| Qwen | HTTPX | NO_MEMORY | 476 | 0 | 0 | 211 | 159 | 17,116 | YES | 15,652 |
| Qwen | HTTPX | SOURCE_CORRECT_MEMORY | 9,825 | 9,335 | 0 | 211 | 159 | 26,465 | YES | 6,303 |
| Qwen | Djoser | NO_MEMORY | 467 | 0 | 0 | 211 | 150 | 17,107 | YES | 15,661 |
| Qwen | Djoser | SOURCE_CORRECT_MEMORY | 2,710 | 2,229 | 0 | 211 | 150 | 19,350 | YES | 13,418 |
| Devstral | MCP Pinot | NO_MEMORY | 516 | 0 | 0 | 224 | 191 | 17,156 | YES | 15,612 |
| Devstral | MCP Pinot | SOURCE_CORRECT_MEMORY | 2,169 | 1,637 | 0 | 224 | 191 | 18,809 | YES | 13,959 |
| Devstral | ONNX | NO_MEMORY | 519 | 0 | 0 | 217 | 201 | 17,159 | YES | 15,609 |
| Devstral | ONNX | SOURCE_CORRECT_MEMORY | 3,043 | 2,508 | 0 | 217 | 201 | 19,683 | YES | 13,085 |
| Devstral | Axios | NO_MEMORY | 471 | 0 | 0 | 213 | 157 | 17,111 | YES | 15,657 |
| Devstral | Axios | SOURCE_CORRECT_MEMORY | 4,894 | 4,407 | 0 | 213 | 157 | 21,534 | YES | 11,234 |
| Devstral | Aim | NO_MEMORY | 467 | 0 | 0 | 213 | 153 | 17,107 | YES | 15,661 |
| Devstral | Aim | SOURCE_CORRECT_MEMORY | 947 | 464 | 0 | 213 | 153 | 17,587 | YES | 15,181 |
| Devstral | HTTPX | NO_MEMORY | 479 | 0 | 0 | 215 | 163 | 17,119 | YES | 15,649 |
| Devstral | HTTPX | SOURCE_CORRECT_MEMORY | 10,268 | 9,773 | 0 | 215 | 163 | 26,908 | YES | 5,860 |
| Devstral | Djoser | NO_MEMORY | 472 | 0 | 0 | 215 | 156 | 17,112 | YES | 15,656 |
| Devstral | Djoser | SOURCE_CORRECT_MEMORY | 2,922 | 2,434 | 0 | 215 | 156 | 19,562 | YES | 13,206 |

All 24 cells fit. The tightest cell is Devstral HTTPX with memory, leaving
5,860 physical tokens after reserving the complete 16,384-token trajectory and
256-token safety margin. Frozen memory text was not shortened.

## 12. CONTEXT_BUDGET_FEASIBILITY

Offline status: `PASS`

V2 profile:

- physical context `C = 32768`;
- post-ingestion budget `B = 16384`;
- reserve `R = 256`;
- per-turn generation ceiling `G = 4096`; and
- maximum decisions `S = 32`.

Exact algorithm:

1. `P` is the full first serialized request, including system prompt, task,
   memory wrapper/content if present, native chat-template tokens, role tokens,
   action/tool contract, and assistant generation prefix.
2. Every turn serializes the complete current transcript and measures `T_t`.
3. `D_t = T_t - P`.
4. `A_t = B - D_t`.
5. `max_new_tokens_t = min(G, A_t)`.
6. If `A_t <= 0`, terminate with `TRAJECTORY_BUDGET_EXHAUSTED` as a scientific
   outcome.

All model-visible assistant text, action syntax, arguments, observations,
role/template tokens, returned command output, and final response consume `B`.
History is never silently removed, summarized, or compacted.

The minimum physical context implied by the largest initial cell is 26,908.
The fixed recommended context remains 32,768.

### Tool output policy

V2 exposes at most 32 KiB of UTF-8 output per tool call. Truncation is
deterministic and preserves both the beginning and end with an explicit marker.
The complete raw output is saved outside model-visible history using exclusive
creation and SHA-256 metadata. The visible truncated representation counts
fully against `B`. Tests cover Unicode boundaries, hash identity, raw
preservation, and the absence of silent history truncation.

## 13. MODEL_ADAPTER_PARITY

Static status: `PASS`

Dynamic status: `NOT_TESTED_NO_GPU`

Equivalent between Qwen and Devstral:

- task and treatment content;
- text-action capabilities and shell policy;
- initial repository/working-directory state;
- patch collection and evaluator routing;
- command and model-response timeout semantics;
- common `C/B/R/G/S` limits;
- output truncation and raw-output policy;
- trajectory-budget and scientific termination policy; and
- synthetic qualification checklist.

Intentional model-native differences:

- tokenizer/chat serialization;
- exact revision and snapshot path;
- server environment and pinned vLLM version;
- Devstral `mistral` load/config formats; and
- qualification TP configuration.

No accidental static asymmetry in task information, capabilities, repository,
patch, evaluation, or logical completion capacity was found. Actual server
parity still requires both GPU qualification runs.

## 14. TECHNICAL_INVALID_POLICY

V2 unit-test status: `PASS`

Scientific outcomes:

- no tool calls;
- refusal;
- model-produced malformed action/tool syntax;
- empty patch;
- functionality/test failure;
- security failure;
- model-chosen command timeout;
- maximum-step exhaustion; and
- `TRAJECTORY_BUDGET_EXHAUSTED`.

Technical invalidities:

- node/machine failure;
- CUDA failure;
- server crash or OOM;
- transport failure;
- harness exception;
- corrupted checkout;
- evaluator infrastructure failure;
- model server unavailable; and
- a parser defect on objectively valid model syntax.

Unknown termination strings fail closed rather than being guessed from outcome
quality. Replacement attempts use new exclusive paths and never overwrite the
original attempt. The V1 replacement implementation was already sound; V2's
exclusive log writer adds a second check.

## 15. LOGGING_AUDIT

Schema status: `PASS`

Live model-runner population: `NOT_TESTED_NO_GPU`

The V2 schema requires:

- run ID, family, masked treatment ID, model, exact revision;
- tokenizer hash, harness commit, server image/version;
- CUDA/driver, GPU name/count, TP degree;
- physical context, `P/B/R`;
- per-turn transcript count and allowed `max_new_tokens`;
- server-reported prompt/completion counts and latency;
- action sequence and arguments;
- command duration and timeout events;
- stdout/stderr truncation metadata and raw-output hashes;
- generated-token count and termination reason;
- final patch hash;
- functionality, task-completion, and security results; and
- technical-validity decision.

Required fields are validated and attempts are written exclusively. What
remains is wiring the schema into a future authorized live V2 runner and
proving every field is populated by both real servers.

## 16. LEAKAGE_AUDIT

Status: `UNRESOLVED`

Evidence: [`leakage-audit.json`](leakage-audit.json)

Proven statically:

- agent working-copy construction omits `oracles/` and `references/`;
- declared hidden/protected paths are blocked by command authorization;
- evaluators run externally against final repository state;
- the proposed evaluator interface does not need treatment labels; and
- rendered prompts contain neither hidden witness nor safe-control content.

Not proven:

- same-user access to paths outside the working copy is prevented by an OS
  boundary;
- hidden controls, witnesses, evaluator sources, and other results are
  inaccessible through all filesystem routes; and
- the exact eventual Slurm mount/container arrangement preserves that boundary.

Required correction: qualify an execution sandbox exposing only the candidate
working copy and required runtime. Policy checks alone are insufficient.

## 17. DETERMINISM_AUDIT

V1 findings:

- request temperature was 0;
- vLLM server seed was 0;
- request seed was null;
- run seeds primarily identified matrix rows; and
- post-primary analysis found identical patches and endpoints in 24/24 seed
  pairs, with 22/24 identical on every compared dimension.

V2 canonical profile:

- `temperature = 0`;
- `do_sample = false`; and
- `top_p = 1`.

No artificial repeated study seeds were introduced. An automated three-repeat
comparison exists for excluded/synthetic tasks and compares full assistant
text, actions, arguments, termination, and patch hash. It is
`NOT_TESTED_NO_GPU`.

## 18. QWEN_V2_QUALIFICATION

Overall: `NOT_TESTED_NO_GPU`

Artifact: [`qualification-qwen.json`](qualification-qwen.json)

Model: `Qwen/Qwen2.5-Coder-32B-Instruct`

Revision: `381fc969f78efac66bc87ff7ddeadb7e73c218a7`

| Check | Status |
|---|---|
| Exact model revision | PASS |
| Exact tokenizer | PASS |
| 32K server command | PASS |
| Synthetic file edit | PASS |
| Synthetic test execution | PASS |
| Synthetic nonempty patch | PASS |
| Output truncation | PASS |
| Logical trajectory budget | PASS |
| Command timeout | PASS |
| No silent history truncation | PASS |
| Server startup | NOT_TESTED_NO_GPU |
| Benign generation | NOT_TESTED_NO_GPU |
| Valid model action/tool call | NOT_TESTED_NO_GPU |
| Multiple model/tool turns | NOT_TESTED_NO_GPU |
| Server/local prompt-token equality | NOT_TESTED_NO_GPU |
| Model-driven edit/test/patch | NOT_TESTED_NO_GPU |
| Model-response timeout | NOT_TESTED_NO_GPU |
| Clean shutdown | NOT_TESTED_NO_GPU |
| Deterministic repeatability | NOT_TESTED_NO_GPU |
| No OOM / no physical truncation | NOT_TESTED_NO_GPU |

No Qwen model inference was run. An older V1 Qwen competence qualification was
2/5 and must not be confused with this V2 technical checklist.

## 19. DEVSTRAL_V2_QUALIFICATION

Overall: `NOT_TESTED_NO_GPU`

Artifact: [`qualification-devstral.json`](qualification-devstral.json)

Model: `mistralai/Devstral-Small-2507`

Revision: `bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39`

| Check | Status |
|---|---|
| Exact model revision | PASS |
| Exact tokenizer | PASS |
| 32K server command | PASS |
| Synthetic file edit | PASS |
| Synthetic test execution | PASS |
| Synthetic nonempty patch | PASS |
| Output truncation | PASS |
| Logical trajectory budget | PASS |
| Command timeout | PASS |
| No silent history truncation | PASS |
| Server startup | NOT_TESTED_NO_GPU |
| Benign generation | NOT_TESTED_NO_GPU |
| Valid model action/tool call | NOT_TESTED_NO_GPU |
| Multiple model/tool turns | NOT_TESTED_NO_GPU |
| Server/local prompt-token equality | NOT_TESTED_NO_GPU |
| Model-driven edit/test/patch | NOT_TESTED_NO_GPU |
| Model-response timeout | NOT_TESTED_NO_GPU |
| Clean shutdown | NOT_TESTED_NO_GPU |
| Deterministic repeatability | NOT_TESTED_NO_GPU |
| No OOM / no physical truncation | NOT_TESTED_NO_GPU |

No Devstral model inference was run. The historical Devstral 4096-token TP2
technical smoke does not qualify this 32K profile.

## 20. HARDWARE_MEASUREMENTS

Status: engineering estimate; runtime measurements `NOT_TESTED_NO_GPU`

Artifact: [`hardware-estimates.json`](hardware-estimates.json), SHA-256
`48aad83d5786cd2aea56de67f92199e72a577c878da4a66a2301337e46e99e80`

The estimates use exact cached weight tensor headers and exact local model
configuration. Formula:

`BF16 weight bytes + BF16 K/V cache + max(4 GiB, 10% weight overhead)`

| Measurement | Qwen2.5-Coder-32B | Devstral-Small-2507 |
|---|---:|---:|
| Architecture | `Qwen2ForCausalLM` | `MistralForCausalLM` |
| Exact parameters | 32,763,876,352 | 23,572,403,200 |
| Weight dtype | BF16 | BF16 |
| Weight tensor bytes | 65,527,752,704 | 47,144,806,400 |
| Weight GiB | 61.0275 | 43.9070 |
| Layers | 64 | 40 |
| Hidden size | 5,120 | 5,120 |
| Attention heads | 40 | 32 |
| KV heads | 8 | 8 |
| Head dimension | 128 | 128 |
| 32K BF16 KV cache, concurrency 1 | 8.00 GiB | 5.00 GiB |
| Estimated runtime overhead | 6.1027 GiB | 4.3907 GiB |
| Estimated total | 75.1302 GiB | 53.2977 GiB |

Conservative TP1 fit at `gpu_memory_utilization=0.90`:

| Hardware | Qwen TP1 | Devstral TP1 |
|---|---|---|
| A100 80 GB | NO | YES |
| H100 80 GB | NO | YES |
| H100 NVL 94 GB | YES | YES |
| H200 141 GB | YES | YES |

Current vLLM documentation lists `Qwen2ForCausalLM` and
`MistralForCausalLM` as supported architectures. That does not replace exact
qualification of the pinned V1/V2 server environments and revisions.

The following requested empirical measurements are all
`NOT_TESTED_NO_GPU`: idle VRAM, model-loaded VRAM, peak VRAM, reported KV-cache
allocation, tokens/second, time to first token, and model startup time.

## 21. TEST_RESULTS

Overall repository result: `FAIL`

Artifact: [`test-results.json`](test-results.json)

| Measurement | Result |
|---|---:|
| Full-suite tests collected | 947 |
| Tests executed across disjoint continuation runs | 879 |
| Failures | 19 |
| Errors | 0 |
| Skipped | 0 |
| Not executed after uninterruptible mount failures | 68 |
| Latest focused V2 suite | 42 |
| Latest focused V2 failures | 0 |
| Latest focused V2 status | PASS |

Failure groups:

- 13 failures from incomplete committed Axios/Aim/HTTPX/Aim frozen snapshots;
- 2 failures from historical job-25692 Python-environment assertions; and
- 4 failures from frozen interpreter/network-mount timeouts.

Additional validation:

- six-family deterministic evaluator/control execution: completed successfully;
- security control behavior: `PASS` for all six safe controls and `FAIL` for
  all six untouched unsafe states, as expected;
- prompt rendering: `PASS`, 24/24 cells;
- exact offline token census: `PASS`, 24/24 fit;
- V2 focused unit/integration tests: `PASS`, 42/42;
- V2 module compilation: `PASS`;
- JSON artifact parse validation: `PASS`;
- final `git diff --check`: `PASS`; and
- final tracked worktree diff: empty.

The complete suite was attempted. Frozen environment interpreters entered
uninterruptible `D` state on network storage, preventing 68 remaining tests
from completing. Five audit-created probe interpreters remained kernel-blocked;
their controllable parent shells were terminated. They did not modify the
repository. Raw JUnit evidence is preserved in the `pytest-*.xml` artifacts.
No failing test was weakened or deleted.

## 22. REMAINING_BLOCKERS

1. `BLOCKED` — `TASK_COMPLETION` is non-identifiable because faithful reuse is
   the same final state as untouched/no-op in all six frozen families.
2. `FAIL` — Axios, Aim, and HTTPX committed family snapshots omit ignored files
   used by V1.
3. `FAIL` — The complete non-study pytest suite is not passing.
4. `UNRESOLVED` — OS-level leakage isolation is not proven.
5. `NOT_TESTED_NO_GPU` — Qwen exact-revision 32K server qualification.
6. `NOT_TESTED_NO_GPU` — Devstral exact-revision 32K server qualification.
7. `NOT_TESTED_NO_GPU` — Three-repeat deterministic server qualification.
8. `NOT_TESTED_NO_GPU` — Actual VRAM, startup, throughput, TTFT, and OOM margin.
9. `NOT_TESTED_NO_GPU` — Live V2 logging-field population and clean shutdown.

The first blocker is scientific and must be resolved before GPU rental alone
can make the study runnable.

## 23. STUDY_RUN_AUTHORIZATION

Status: `FAIL`

`study_run_authorized = false`

The authoritative decision is in [`readiness.json`](readiness.json). Current
key fields:

| Field | Value |
|---|---|
| `all_tests_pass` | `false` |
| `task_completion_ready` | `false` |
| `security_controls_ready` | `true` |
| `token_census_ready` | `true` |
| `all_prompts_fit_32768` | `true` |
| `qwen_qualification_status` | `NOT_TESTED_NO_GPU` |
| `devstral_qualification_status` | `NOT_TESTED_NO_GPU` |
| `leakage_audit_status` | `UNRESOLVED` |
| `determinism_status` | `NOT_TESTED_NO_GPU` |
| `study_run_authorized` | `false` |

No V2 six-family inference may begin from this state.

## 24. RECOMMENDED_GPU_MINIMUMS

These are engineering-estimated capacity minimums, not a provider or rental
duration recommendation.

### Qwen2.5-Coder-32B-Instruct

- Estimated 32K concurrency-1 requirement: 75.13 GiB before additional
  qualification margin.
- Conservative TP1 physical minimum: 94 GB.
- A100/H100 80 GB: use TP2; TP1 is not recommended at 90% allocator target.
- H100 NVL 94 GB or H200 141 GB: TP1 is expected to fit, subject to actual
  vLLM qualification.

### Devstral-Small-2507

- Estimated 32K concurrency-1 requirement: 53.30 GiB.
- Conservative TP1 physical minimum: 80 GB.
- TP2 is not expected to be necessary for capacity on an 80 GB GPU.

### Common target

- One GPU capable of either model at TP1: at least 94 GB physical VRAM.
- If only 80 GB GPUs are available: Qwen TP2, Devstral TP1.
- Physical context: 32,768.
- Qualification/study concurrency: 1.

## 25. FINAL_STATE

Repository hygiene: `PASS`

Study readiness: `FAIL`

- Branch: `feat/v2-audit-and-qualification`
- Pre-report evidence HEAD: `4bc528bfacb90661ce570440b71496a242b1b275`
- Worktree was clean before adding this report.
- Final report commit is the commit containing this file; obtain the exact hash
  with `git log -1 --format=%H -- artifacts/v2-preflight/v2-preflight-report.md`.
- `git diff --check`: `PASS` after final commit.
- Final tracked worktree diff: empty after final commit.
- Original authoritative working tree: unchanged.
- V1 artifacts, memories, evaluators, controls, and witnesses: unchanged.
- No V2 study-family inference executed.

## 26. COMMIT

Coherent V2 audit commits:

1. `c0c8d8d4a` — `Import frozen historical family audit inputs`
2. `0dc968da1` — `Add V2 preflight and qualification infrastructure`
3. `4bc528bfa` — `Record V2 preflight audit evidence`
4. Report commit — the commit containing
   `artifacts/v2-preflight/v2-preflight-report.md`; resolve with the path-limited
   `git log` command in section 25.

Nothing was merged into a V1 branch. The report commit adds documentation only
and does not change the readiness decision in [`readiness.json`](readiness.json).
