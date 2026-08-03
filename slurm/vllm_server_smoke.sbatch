#!/usr/bin/env bash
#SBATCH --job-name=vllm-smoke-2
#SBATCH --partition=gpu
#SBATCH --gres=gpu:rtxa4000ada:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=00:20:00
#SBATCH --output=/home/s224049759/slurm-logs/vllm-server-smoke-%j.out
#SBATCH --error=/home/s224049759/slurm-logs/vllm-server-smoke-%j.err

set -euo pipefail

PROJECT=/home/s224049759/projects/correct-memory-study
VENV=/home/s224049759/environments/vllm-smoke
ARTIFACT_ROOT=/home/s224049759/run-artifacts/vllm-smoke-2
MODEL=Qwen/Qwen2.5-Coder-1.5B-Instruct
REVISION=2e1fd397ee46e1388853d2af2c993145b0f1098a
ARTIFACT_DIR="$ARTIFACT_ROOT/$SLURM_JOB_ID"
SERVER_PID=
SERVER_CLEANUP_COMPLETE=0

mkdir -p "$ARTIFACT_DIR"
printf 'job_started_at=%s\n' "$(date --iso-8601=seconds)" > "$ARTIFACT_DIR/timestamps.txt"

terminate_server() {
    local cleanup_status=0
    local remaining=
    if [ -z "$SERVER_PID" ]; then
        echo "no_server_pid_recorded" >> "$ARTIFACT_DIR/process-cleanup.txt"
        return 0
    fi
    echo "server_pid=$SERVER_PID" >> "$ARTIFACT_DIR/process-cleanup.txt"
    if kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "sending_graceful_SIGTERM_to_process_group" >> "$ARTIFACT_DIR/process-cleanup.txt"
        kill -TERM -- "-$SERVER_PID" 2>/dev/null || cleanup_status=1
        for _ in $(seq 1 30); do
            if ! kill -0 "$SERVER_PID" 2>/dev/null; then
                break
            fi
            sleep 1
        done
        if kill -0 "$SERVER_PID" 2>/dev/null; then
            echo "graceful_timeout_force_kill" >> "$ARTIFACT_DIR/process-cleanup.txt"
            kill -KILL -- "-$SERVER_PID" 2>/dev/null || cleanup_status=1
        else
            echo "graceful_termination_confirmed" >> "$ARTIFACT_DIR/process-cleanup.txt"
        fi
    else
        echo "server_already_exited" >> "$ARTIFACT_DIR/process-cleanup.txt"
    fi
    wait "$SERVER_PID" 2>/dev/null || true
    remaining=$(ps -eo pid=,pgid=,args= | awk -v group="$SERVER_PID" '$2 == group {print}')
    if [ -n "$remaining" ]; then
        echo "remaining_server_process_group_members:" >> "$ARTIFACT_DIR/process-cleanup.txt"
        printf '%s\n' "$remaining" >> "$ARTIFACT_DIR/process-cleanup.txt"
        cleanup_status=1
    else
        echo "no_server_process_remains" >> "$ARTIFACT_DIR/process-cleanup.txt"
    fi
    SERVER_CLEANUP_COMPLETE=1
    return "$cleanup_status"
}

on_exit() {
    status=$?
    set +e
    if [ "$SERVER_CLEANUP_COMPLETE" -ne 1 ]; then
        terminate_server || status=1
    fi
    nvidia-smi > "$ARTIFACT_DIR/nvidia-smi-after.txt"
    printf 'job_finished_at=%s\n' "$(date --iso-8601=seconds)" >> "$ARTIFACT_DIR/timestamps.txt"
    printf 'job_exit_status=%s\n' "$status" >> "$ARTIFACT_DIR/timestamps.txt"
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
mkdir -p "$HF_HOME"

{
    printf 'VIRTUAL_ENV=%s\n' "$VIRTUAL_ENV"
    printf 'HF_HOME=%s\n' "$HF_HOME"
    printf 'HF_HUB_DISABLE_TELEMETRY=%s\n' "$HF_HUB_DISABLE_TELEMETRY"
    printf 'TOKENIZERS_PARALLELISM=%s\n' "$TOKENIZERS_PARALLELISM"
    printf 'PYTHONNOUSERSITE=%s\n' "$PYTHONNOUSERSITE"
    printf 'python=%s\n' "$(command -v python)"
    python --version
    python -c "from importlib.metadata import version; print('vllm=' + version('vllm'))"
} > "$ARTIFACT_DIR/environment.txt"
env | awk -F= '$1 ~ /^SLURM_/ {print}' | sort > "$ARTIFACT_DIR/slurm-environment.txt"
python -m pip freeze | sort > "$ARTIFACT_DIR/pip-freeze.txt"
printf '%s\n' "$REVISION" > "$ARTIFACT_DIR/model-revision.txt"
printf '%s\n' "generation-config=vllm unsupported by vLLM 0.6.1.post2 CLI; request uses temperature=0" \
    > "$ARTIFACT_DIR/compatibility-note.txt"
python "$PROJECT/scripts/check_vllm_guided_decoding_deps.py" \
    > "$ARTIFACT_DIR/guided-decoding-dependency-check.txt" 2>&1

nvidia-smi > "$ARTIFACT_DIR/nvidia-smi-before.txt"
nvidia-smi topo -m > "$ARTIFACT_DIR/nvidia-smi-topology.txt"
printf '%q ' vllm serve "$MODEL" --revision "$REVISION" --host 127.0.0.1 --port 8000 \
    --dtype bfloat16 --max-model-len 4096 --gpu-memory-utilization 0.70 \
    --guided-decoding-backend lm-format-enforcer \
    > "$ARTIFACT_DIR/server-command.txt"
printf '\n' >> "$ARTIFACT_DIR/server-command.txt"

server_launch_epoch=$(python -c 'import time; print(time.time())')
printf 'server_launch_at=%s\n' "$(date --iso-8601=seconds)" >> "$ARTIFACT_DIR/timestamps.txt"
setsid vllm serve "$MODEL" \
    --revision "$REVISION" \
    --host 127.0.0.1 \
    --port 8000 \
    --dtype bfloat16 \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.70 \
    --guided-decoding-backend lm-format-enforcer \
    > "$ARTIFACT_DIR/server.stdout.log" \
    2> "$ARTIFACT_DIR/server.stderr.log" &
SERVER_PID=$!
printf '%s\n' "$SERVER_PID" > "$ARTIFACT_DIR/server.pid"

python "$PROJECT/scripts/vllm_server_smoke_client.py" \
    --artifact-dir "$ARTIFACT_DIR" \
    --server-pid "$SERVER_PID" \
    --server-launch-epoch "$server_launch_epoch" \
    > "$ARTIFACT_DIR/client.stdout.log" \
    2> "$ARTIFACT_DIR/client.stderr.log"
printf 'client_finished_at=%s\n' "$(date --iso-8601=seconds)" >> "$ARTIFACT_DIR/timestamps.txt"

terminate_server
nvidia-smi > "$ARTIFACT_DIR/nvidia-smi-after.txt"
printf 'server_cleanup_finished_at=%s\n' "$(date --iso-8601=seconds)" >> "$ARTIFACT_DIR/timestamps.txt"
