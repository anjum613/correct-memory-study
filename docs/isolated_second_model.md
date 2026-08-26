# Isolated second-model implementation record

Recorded on 2026-08-26 in
`/home/anjum/Documents/research/correct-memory-study`.

## Starting state and baseline

- Starting branch: `main`
- Starting HEAD: `47f283105b9faa45803a120898b16a932115e5ae`
- Starting tracked and untracked state: clean
- `git status --short`: no output
- `git diff --check`: passed
- Implementation branch: `feat/isolated-second-model-support`
- Baseline test command: `python -m pytest -q`
- Baseline result: 47 passed in 1.68 seconds
- Baseline compile command: `python -m compileall -q src tests scripts`
- Baseline launcher syntax: `bash -n scripts/start_vllm_smoke.sh`
- Primary smoke launcher SHA-256:
  `add1c50f9a948d6b1a6f6db5ab8dabafa8cf2609688739395392612bcfe44132`
- Shared mini-SWE adapter-source SHA-256:
  `ca6cb326858e49f5a563f3607ce23800b3dca321264a4d1431cbe62b10bebfcf`

The checkout did not contain a committed Qwen2.5-Coder-32B production
launcher, production triplets, memory constructor, security witnesses,
production manifest, recovery implementation, or Slurm submission script.
Its only launch path was the Qwen2.5-Coder-1.5B engineering smoke in
`scripts/start_vllm_smoke.sh`. The implementation therefore treats the 32B
primary entry as an attestation-only reference and does not invent or replace
an absent primary launch configuration.

The active and repository virtual-environment interpreters were both Python
3.14.7. PyTorch, Transformers, vLLM, tokenizers, and Hugging Face Hub were not
installed. No Conda environment, CUDA compiler, NVIDIA runtime, Singularity,
or Apptainer was available. The existing README records a separate
`vllm-v0.6.6.post1.sif` path, but the image and its package versions are not in
this repository and were not modified. No explicit existing Hugging Face cache
path was configured.

## Existing responsibility map

- Model selection: `src/cmpilot/smoke_runner.py` (`resolve_config`)
- Existing server startup and Hermes tool parser:
  `scripts/start_vllm_smoke.sh`
- Tokenizer/chat serialization and OpenAI request: vLLM plus the pinned
  mini-SWE-agent/LiteLLM adapter in `src/cmpilot/mini_swe_adapter.py`
- Action parsing: mini-SWE-agent 2.4.6 external dependency; there is no local
  production parser module
- OpenAI-compatible `/v1/models` request: `src/cmpilot/vllm_client.py`
- Run IDs and output-directory creation: `src/cmpilot/artifact_logger.py`
- Manifests and finalization: `src/cmpilot/smoke_runner.py`
- Repository setup: `src/cmpilot/repository_manager.py`
- Outcome classification: `src/cmpilot/outcome_classifier.py`
- Revision attestation, cache keys, memory-artifact construction, incomplete
  run recovery, production Slurm submission: absent at baseline

## Bounded candidate assessment

Devstral Small 2507 was selected. Its official model card documents a 128K
context, vLLM serving, the Mistral tokenizer/config/load formats, native Mistral
tool parsing, automatic tool choice, and TP=2. The exact attested model and
tokenizer revision is:

`mistralai/Devstral-Small-2507@bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39`

The pinned snapshot's `config.json` reports BF16 and
`max_position_embeddings=131072`. vLLM 0.10.0 with `mistral-common` 1.8.4 was
chosen because that release line contains v13 Tekken tokenizer support. The
profile uses non-streaming OpenAI Chat Completions through the unchanged
mini-SWE adapter, so the separate reported streaming parser issue is not on
this path.

Qwen3-32B was not selected because Devstral has the required serving and tool
interfaces and provides model-family diversity. If Qwen3 is used later, it
must be a separate profile with tokenizer-level `enable_thinking=False` and a
new label. Qwen2.5-32B-Instruct remains the lower-risk fallback but was not
needed for this CPU-side implementation.

Official references:

- <https://huggingface.co/mistralai/Devstral-Small-2507>
- <https://github.com/vllm-project/vllm/pull/20905>
- <https://docs.vllm.ai/en/v0.9.1/getting_started/installation/gpu.html>

## Isolation

The launchable profile is
`configs/model_profiles/devstral-small-2507.toml`. The primary 32B reference is
non-launchable by design, so it cannot acquire guessed defaults. An explicit
Devstral run resolves to:

```text
<runs-root>/non-confirmatory/
  devstral-small-2507-bd165ab26ceb/
  cmpilot-devstral-small-2507-v1-cu128/
  smoke-devstral-small-2507-bd165ab26ceb-<timestamp>-<random>/
```

The run manifest, model-info artifact, resolved configuration, run ID, and
directory path all contain the profile, model/tokenizer revisions, served
identity, environment identity, generation configuration, and server
configuration. Unprofiled smoke runs retain their original run IDs, output
root, and manifest shape.

The shared weight cache uses the exact immutable snapshot key:

```text
$CMPILOT_SHARED_CACHE_ROOT/huggingface/hub/
models--mistralai--Devstral-Small-2507/snapshots/
bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39/
```

vLLM, Triton, and TorchInductor caches are separate under
`$CMPILOT_SHARED_CACHE_ROOT/runtime/devstral-small-2507-bd165ab26ceb/`.
The launcher sets Hub and Transformers offline modes and refuses an incomplete
snapshot instead of downloading weights. The engineering smoke has no memory
condition or memory artifact; the absent production methodology was not
invented.

## Separate environment

Create and activate only the new environment:

```bash
DEVSTRAL_BOOTSTRAP_PYTHON=/path/to/python3.11 \
DEVSTRAL_ENV_DIR="$PWD/.runtime/devstral-small-2507" \
scripts/create_devstral_environment.sh
source "$PWD/.runtime/devstral-small-2507/bin/activate"
```

Pinned versions are Python 3.11.11, pip 25.1.1, PyTorch/torchaudio 2.7.1,
torchvision 0.22.1, vLLM 0.10.0, Transformers 4.53.2, tokenizers 0.21.2,
Hugging Face Hub 0.33.4, `mistral-common` 1.8.4, xgrammar 0.1.21, and
outlines-core 0.2.10, using CUDA 12.8 wheels. The creation script ends with
`pip check`; the verifier repeats package checks, loads the exact offline
tokenizer, renders a native Bash-tool template, records its digest, checks
CUDA, and requires exactly two A100s when requested.

The existing `.venv`, external primary environment, and existing Singularity
launch configuration are never activated, upgraded, or written by these
scripts.

## Bounded smoke submission

Prepare the Slurm log directory, substitute the three site-specific absolute
paths, and submit exactly one two-GPU job:

```bash
mkdir -p logs/devstral-small-2507
sbatch --export=ALL,\
DEVSTRAL_ENV_DIR=/absolute/path/to/devstral-env,\
MINI_SWE_PYTHON=/absolute/path/to/unchanged-mini-swe-2.4.6/python,\
CMPILOT_SHARED_CACHE_ROOT=/absolute/path/to/shared-cache,\
CMPILOT_RUNS_ROOT=/absolute/path/to/non-confirmatory-runs \
slurm/devstral_smoke_2gpu.sbatch
```

Inspect a submitted job with:

```bash
squeue -j <JOB_ID> -o '%i|%j|%T|%D|%b|%l|%S|%o'
```

The job requests one node, two GPUs constrained to A100, TP=2, and 45 minutes.
It records environment and revision attestations, `/health`, exact
`/v1/models` identity, five-second GPU-memory samples, the unchanged action
parser diagnostic, dry-run preflight, one live calculator attempt, finalizer,
manifest, and cleanup. It is explicitly non-confirmatory. A four-GPU job has
not been prepared because two-GPU memory pressure has not been demonstrated;
the dedicated launcher permits TP=4 only when given an existing two-GPU
failure log.

On the implementation host, `scontrol ping` reported
`Slurmctld(primary) at fedora is DOWN`, `squeue` could not contact the
controller, and `sbatch --test-only` could not validate GPU GRES against the
unavailable controller/configuration. No job ID exists and no smoke has been
claimed as queued or passed.

## Material blockers

The repository is not yet capable of the requested confirmatory replication:

1. The exact mini-SWE-agent 2.4.6 parser rejects missing, malformed, missing-
   command, and wrong-tool calls, but it accepts literal placeholder commands
   and multiple Bash tool calls. The new diagnostic records this behavior
   without executing commands. Changing it would violate the instruction not
   to change the primary action grammar/parser, so this remains visible rather
   than being silently repaired.
2. The checkout has no production six-family runner, memory/no-memory
   constructor, functionality/security triplets, security witness, production
   finalizer/recovery implementation, or array shard entrypoint. There is no
   truthful six-family production command to provide. A production array was
   deliberately not fabricated.
3. The isolated environment, cached model weights, A100 runtime, and model-
   backed action/end-to-end diagnostics cannot be exercised on this host.
4. The Slurm controller is down/unreachable, so the bounded smoke is prepared
   but neither queued nor passed. Peak GPU memory and startup duration are not
   available.

Do not launch a production experiment until these blockers are resolved and
the bounded compatibility smoke passes without changes to the shared prompts
or parser.
