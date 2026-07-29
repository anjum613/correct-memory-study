# correct-memory-study
Controlled procedural-memory transfer experiments for coding agents

## Development setup (Fish shell)

```fish
python3 -m venv .venv
source .venv/bin/activate.fish
python -m pip install -e ".[dev]"
```

## Engineering smoke test

This is an engineering-only calculator check. Codex builds and tests the
harness; **mini-SWE-agent alone performs the evaluated calculator repair** in a
fresh copy of the template. There are no procedural memories, treatment
conditions, security witnesses, or security-triplet changes in this workflow.
It launches the agent once and preserves both failures and successes; it never
retries or selects a favorable run.

The live run is deliberately opt-in: use `--dry-run` first, then add `--live`
only when you intend to make one model-backed run. The harness gives that child
an isolated `HOME`, temporary directory, and no inherited API-key variables.
Run it only on a non-sensitive account: mini-SWE-agent's required local Bash
environment can execute commands in its isolated calculator working copy.

mini-SWE-agent 2.4.6's documented `DefaultAgent`/`LitellmModel` integration
uses a native Bash tool definition. Native tool calls are therefore required.
vLLM 0.6.6 requires `--enable-auto-tool-choice` and a parser for auto tool
choice; Qwen's Qwen2.5 vLLM guidance uses the `hermes` parser. The launcher
uses those two flags for that reason, not as an unverified optional tweak.

### Deakin two-terminal workflow

Activate the `cmpilot` environment with the shell appropriate to your setup.
The repository's existing Fish setup is shown above; in Bash use
`source .venv/bin/activate` instead.

Terminal 1 — start vLLM and leave it running:

```bash
source .venv/bin/activate
export VLLM_SINGULARITY_IMAGE=/mnt/data/anjum/cmpilot/images/vllm-v0.6.6.post1.sif
export VLLM_LOG_DIR=/mnt/data/anjum/vllm-smoke-logs
export VLLM_MODEL=Qwen/Qwen2.5-Coder-1.5B-Instruct
export VLLM_DTYPE=half
scripts/start_vllm_smoke.sh
```

The helper first checks port 8000. If the expected healthy server is already
there it exits successfully; if another or unhealthy service owns the port, it
prints a reason and does not kill anything. Otherwise it stays in the
foreground and writes a timestamped log under `VLLM_LOG_DIR`. Stop it cleanly
with `Ctrl-C` in this terminal. The launcher sets Hugging Face/Transformers
offline mode, so it will not download a model; the smoke model must already be
present in the workstation cache. The Quadro RTX 5000 requires float16
(`half`) rather than bfloat16, which its Turing-generation GPU does not
support.

Terminal 2 — verify and run one smoke test:

```bash
source .venv/bin/activate
export VLLM_BASE_URL=http://127.0.0.1:8000/v1
export VLLM_MODEL=Qwen/Qwen2.5-Coder-1.5B-Instruct
export MINI_SWE_PYTHON=/mnt/data/anjum/mini-swe-env/bin/python
export CMPILOT_RUNS_ROOT=/mnt/data/anjum/experiment-runs

python -m cmpilot doctor
python -m cmpilot smoke --dry-run
python -m cmpilot smoke --live
```

CLI values override these environment variables, so the equivalent explicit
invocation is:

```bash
python -m cmpilot smoke \
  --live \
  --base-url http://127.0.0.1:8000/v1 \
  --model Qwen/Qwen2.5-Coder-1.5B-Instruct \
  --mini-python /mnt/data/anjum/mini-swe-env/bin/python \
  --runs-root /mnt/data/anjum/experiment-runs
```

The isolated calculator's three tests are expected to fail initially with
`NotImplementedError`. A successful run then has all three tests passing. Each
attempt, including preflight and agent failures, has a unique directory such
as `experiment-runs/smoke-YYYYMMDD-HHMMSS-<short-id>/`. It contains the clean
`working-copy`, preflight/configuration metadata, complete agent stdout and
stderr, the mini-SWE native trajectory path, the final patch, test outputs,
Git status, and a conservative classification. Inspect a completed attempt
with, for example:

```bash
less /mnt/data/anjum/experiment-runs/smoke-*/trajectory.json
git -C /mnt/data/anjum/experiment-runs/smoke-*/working-copy diff
less /mnt/data/anjum/experiment-runs/smoke-*/final.patch
```

### Troubleshooting

- **Address already in use:** do not kill the listener. Run
  `scripts/start_vllm_smoke.sh` again: it reports whether port 8000 already
  has the expected healthy model or why the occupant is unsuitable. Choose a
  different unused `VLLM_PORT` only if you also update `VLLM_BASE_URL`.
- **`Configured vLLM endpoint responds: false`:** run
  `python -m cmpilot doctor` and read its diagnostic line. It distinguishes
  connection refusal, timeout, non-200 responses, invalid JSON, and missing
  models. The requested endpoint is always `<base-url>/models`, normalized to
  `/v1/models`; it is never the bare `/v1` URL.
- **Mini-SWE-agent preflight fails:** check that `MINI_SWE_PYTHON` points to
  the 2.4.6 environment. The command records the version found and refuses a
  different version rather than guessing a compatible interface.
- **No live run during tests:** `pytest`, `doctor`, and `smoke --dry-run` do
  not launch a model or agent. Only `python -m cmpilot smoke --live` does.
