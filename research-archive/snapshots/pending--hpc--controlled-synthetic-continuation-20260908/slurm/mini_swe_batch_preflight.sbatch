#!/usr/bin/env bash
#SBATCH --job-name=mini-swe-env-check
#SBATCH --partition=Virtual
#SBATCH --account=hpc
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:03:00
#SBATCH --output=/home/s224049759/slurm-logs/mini-swe-batch-preflight-%j.out
#SBATCH --error=/home/s224049759/slurm-logs/mini-swe-batch-preflight-%j.err

set -euo pipefail

PROJECT=/home/s224049759/projects/correct-memory-study
CMPILOT_PY=/home/s224049759/environments/cmpilot-conda/bin/python
MINI_PY=/home/s224049759/environments/mini-swe-agent-smoke/bin/python
MINI_CLI=/home/s224049759/environments/mini-swe-agent-smoke/bin/mini
VLLM_PY=/home/s224049759/environments/vllm-smoke/bin/python
VLLM_BIN=/home/s224049759/environments/vllm-smoke/bin/vllm
UV_BIN=/home/s224049759/.local/bin/uv
ARTIFACT_ROOT=/home/s224049759/run-artifacts/mini-swe-batch-preflight
ARTIFACT_DIR="$ARTIFACT_ROOT/$SLURM_JOB_ID"
export HF_HOME=/home/s224049759/model-cache/huggingface
export HF_HUB_DISABLE_TELEMETRY=1
export TOKENIZERS_PARALLELISM=false
export PYTHONNOUSERSITE=1
export NO_PROXY=127.0.0.1,localhost

mkdir -p "$ARTIFACT_ROOT"
mkdir "$ARTIFACT_DIR"
exec > >(tee "$ARTIFACT_DIR/preflight.stdout.log") \
    2> >(tee "$ARTIFACT_DIR/preflight.stderr.log" >&2)
printf 'preflight_started_at=%s\n' "$(date --iso-8601=seconds)" > "$ARTIFACT_DIR/timestamps.txt"

on_exit() {
    local status=$?
    set +e
    printf 'preflight_finished_at=%s\n' "$(date --iso-8601=seconds)" >> "$ARTIFACT_DIR/timestamps.txt"
    printf 'exit_status=%s\n' "$status" >> "$ARTIFACT_DIR/timestamps.txt"
    if [ "$status" -eq 0 ]; then
        printf 'status=PASS\nexit_status=0\n' > "$ARTIFACT_DIR/result.txt"
    else
        printf 'status=FAIL\nexit_status=%s\n' "$status" > "$ARTIFACT_DIR/result.txt"
    fi
    trap - EXIT
    exit "$status"
}
trap on_exit EXIT

hostname -f > "$ARTIFACT_DIR/hostname.txt"
git -C "$PROJECT" rev-parse HEAD > "$ARTIFACT_DIR/git-commit.txt"
git -C "$PROJECT" --no-pager status --short --branch > "$ARTIFACT_DIR/project-git-status.txt"
cp -- "$0" "$ARTIFACT_DIR/submitted-script.sbatch"
printf 'PATH=%s\n' "$PATH" > "$ARTIFACT_DIR/path.txt"
env | LC_ALL=C sort > "$ARTIFACT_DIR/environment.txt"
env | grep '^SLURM_' | LC_ALL=C sort > "$ARTIFACT_DIR/slurm-environment.txt"

if type module >/dev/null 2>&1; then
    module list > "$ARTIFACT_DIR/module-list.txt" 2>&1
else
    printf 'module command unavailable; no modules are required\n' > "$ARTIFACT_DIR/module-list.txt"
fi

test -x "$CMPILOT_PY"
test -x "$MINI_PY"
test -x "$VLLM_PY"
test -x "$VLLM_BIN"
test -x "$MINI_CLI"
test -x "$UV_BIN"

{
    printf 'CMPILOT_PY=%s\n' "$(readlink -f "$CMPILOT_PY")"
    printf 'MINI_PY=%s\n' "$(readlink -f "$MINI_PY")"
    printf 'VLLM_PY=%s\n' "$(readlink -f "$VLLM_PY")"
    printf 'VLLM_BIN=%s\n' "$(readlink -f "$VLLM_BIN")"
    printf 'MINI_CLI=%s\n' "$(readlink -f "$MINI_CLI")"
    printf 'UV_BIN=%s\n' "$(readlink -f "$UV_BIN")"
} > "$ARTIFACT_DIR/executable-paths.txt"

{
    printf 'cmpilot: '
    "$CMPILOT_PY" --version
    printf 'mini-swe-agent: '
    "$MINI_PY" --version
    printf 'vllm: '
    "$VLLM_PY" --version
} > "$ARTIFACT_DIR/python-versions.txt" 2>&1

"$CMPILOT_PY" - <<'PY' > "$ARTIFACT_DIR/cmpilot-package.txt"
from importlib.metadata import version
print("cmpilot:", version("cmpilot"))
PY

"$MINI_PY" - <<'PY' > "$ARTIFACT_DIR/mini-swe-package.txt"
from importlib.metadata import version
print("mini-swe-agent:", version("mini-swe-agent"))
PY

"$VLLM_PY" - <<'PY' > "$ARTIFACT_DIR/vllm-package-and-imports.txt"
from importlib.metadata import version

for package in [
    "vllm",
    "transformers",
    "lm-format-enforcer",
    "torch",
    "triton",
]:
    print(package, version(package))

import vllm
import lmformatenforcer
print("vLLM imports: PASS")
PY

mkdir "$ARTIFACT_DIR/mini-cli-home"
HOME="$ARTIFACT_DIR/mini-cli-home" \
XDG_CONFIG_HOME="$ARTIFACT_DIR/mini-cli-home/config" \
"$MINI_CLI" --help > "$ARTIFACT_DIR/mini-swe-help.txt" 2>&1

"$CMPILOT_PY" -m cmpilot smoke --help > "$ARTIFACT_DIR/cmpilot-smoke-help.txt" 2>&1

"$CMPILOT_PY" -m pip freeze | LC_ALL=C sort > "$ARTIFACT_DIR/pip-freeze-cmpilot.txt"
"$UV_BIN" pip check --python "$MINI_PY" > "$ARTIFACT_DIR/agent-environment-check.txt" 2>&1
"$UV_BIN" pip freeze --python "$MINI_PY" | LC_ALL=C sort > "$ARTIFACT_DIR/pip-freeze-agent.txt"
"$VLLM_PY" -m pip freeze | LC_ALL=C sort > "$ARTIFACT_DIR/pip-freeze-vllm.txt"

printf 'CPU batch preflight passed; no server started and no model loaded.\n'
