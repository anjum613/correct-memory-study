#!/usr/bin/env bash
#SBATCH --job-name=vllm-batch-preflight
#SBATCH --partition=Virtual
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=00:05:00
#SBATCH --output=/home/s224049759/slurm-logs/vllm-batch-preflight-%j.out
#SBATCH --error=/home/s224049759/slurm-logs/vllm-batch-preflight-%j.err

set -euo pipefail

PROJECT=/home/s224049759/projects/correct-memory-study
VENV=/home/s224049759/environments/vllm-smoke
ARTIFACT_ROOT=/home/s224049759/run-artifacts/vllm-batch-preflight
ARTIFACT_DIR="$ARTIFACT_ROOT/$SLURM_JOB_ID"

mkdir -p "$ARTIFACT_DIR"
printf "job_started_at=%s\n" "$(date --iso-8601=seconds)" > "$ARTIFACT_DIR/timestamps.txt"

on_exit() {
    local status=$?
    set +e
    if ps -ef | grep "[v]llm serve" > "$ARTIFACT_DIR/server-process-check.txt"; then
        printf "ERROR: unexpected vLLM server process observed\n" > "$ARTIFACT_DIR/process-cleanup.txt"
        status=1
    else
        printf "no_server_started_by_cpu_preflight\nno_server_process_remains\n" > "$ARTIFACT_DIR/process-cleanup.txt"
    fi
    printf "job_finished_at=%s\n" "$(date --iso-8601=seconds)" >> "$ARTIFACT_DIR/timestamps.txt"
    printf "job_exit_status=%s\n" "$status" >> "$ARTIFACT_DIR/timestamps.txt"
    trap - EXIT
    exit "$status"
}
trap on_exit EXIT

hostname -f > "$ARTIFACT_DIR/hostname.txt"
git -C "$PROJECT" rev-parse HEAD > "$ARTIFACT_DIR/git-commit.txt"
git -C "$PROJECT" --no-pager status --short --branch > "$ARTIFACT_DIR/git-status.txt"

# shellcheck disable=SC1091
source "$PROJECT/scripts/vllm_smoke_batch_bootstrap.sh"
if vllm_smoke_bootstrap "$ARTIFACT_DIR" "$VENV"; then
    :
else
    bootstrap_status=$?
    printf "bootstrap_exit_status=%s\n" "$bootstrap_status" >> "$ARTIFACT_DIR/batch-shell-preflight.txt"
    exit "$bootstrap_status"
fi

export HF_HOME=/home/s224049759/model-cache/huggingface
export HF_HUB_DISABLE_TELEMETRY=1
export TOKENIZERS_PARALLELISM=false
export PYTHONNOUSERSITE=1

{
    printf "VIRTUAL_ENV=%s\n" "$VIRTUAL_ENV"
    printf "HF_HOME=%s\n" "$HF_HOME"
    printf "python=%s\n" "$(command -v python)"
    python --version
    python -c 'from importlib.metadata import version; print("vllm=" + version("vllm"))'
} > "$ARTIFACT_DIR/environment.txt"
env | grep "^SLURM_" | sort > "$ARTIFACT_DIR/slurm-environment.txt"
python -m pip freeze | sort > "$ARTIFACT_DIR/pip-freeze.txt"
python -m pip check > "$ARTIFACT_DIR/pip-check.txt" 2>&1
python "$PROJECT/scripts/check_vllm_guided_decoding_deps.py" > "$ARTIFACT_DIR/guided-decoding-dependency-check.txt" 2>&1
printf "cpu_preflight=PASS\nmodel_or_vllm_server_started=false\n" > "$ARTIFACT_DIR/result.txt"
