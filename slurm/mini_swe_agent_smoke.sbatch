#!/usr/bin/env bash
#SBATCH --job-name=mini-swe-smoke
#SBATCH --partition=gpu
#SBATCH --gres=gpu:rtxa4000ada:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=00:20:00
#SBATCH --output=/home/s224049759/slurm-logs/mini-swe-agent-smoke-%j.out
#SBATCH --error=/home/s224049759/slurm-logs/mini-swe-agent-smoke-%j.err

set -euo pipefail

PROJECT=/home/s224049759/projects/correct-memory-study
VLLM_ENV=/home/s224049759/environments/vllm-smoke
AGENT_ENV=/home/s224049759/environments/mini-swe-agent-smoke
HARNESS_ENV=/home/s224049759/environments/cmpilot-conda
UV=/home/s224049759/.local/bin/uv
ARTIFACT_ROOT=/home/s224049759/run-artifacts/mini-swe-smoke-3
MODEL=Qwen/Qwen2.5-Coder-1.5B-Instruct
REVISION=2e1fd397ee46e1388853d2af2c993145b0f1098a
ARTIFACT_DIR="$ARTIFACT_ROOT/$SLURM_JOB_ID"
WORK_ROOT="/tmp/$USER/mini-swe-smoke-$SLURM_JOB_ID"
INNER_RUNS="$WORK_ROOT/agent-runs"
SERVER_PID=
SERVER_CLEANUP_COMPLETE=0
RESULT_FINALIZED=0
AGENT_PROCESS_EXIT=125

mkdir -p "$ARTIFACT_DIR" "$WORK_ROOT" "$INNER_RUNS"
printf 'job_started_at=%s\n' "$(date --iso-8601=seconds)" > "$ARTIFACT_DIR/timestamps.txt"

preserve_agent_artifacts() {
    local run_directory=
    if [ ! -d "$INNER_RUNS" ]; then
        return 0
    fi
    run_directory=$(find "$INNER_RUNS" -mindepth 1 -maxdepth 1 -type d -name 'smoke-*' -print | sort | head -n 1)
    if [ -n "$run_directory" ]; then
        cp -a "$run_directory/." "$ARTIFACT_DIR/"
        printf '%s\n' "$run_directory" > "$ARTIFACT_DIR/temporary-agent-run-path.txt"
    fi
}

terminate_server() {
    local cleanup_status=0
    local remaining=
    if [ -z "$SERVER_PID" ]; then
        printf 'no_server_pid_recorded\n' >> "$ARTIFACT_DIR/process-cleanup.txt"
        SERVER_CLEANUP_COMPLETE=1
        return 0
    fi
    printf 'server_pid=%s\n' "$SERVER_PID" >> "$ARTIFACT_DIR/process-cleanup.txt"
    if kill -0 "$SERVER_PID" 2>/dev/null; then
        printf 'sending_graceful_SIGTERM_to_process_group\n' >> "$ARTIFACT_DIR/process-cleanup.txt"
        kill -TERM -- "-$SERVER_PID" 2>/dev/null || cleanup_status=1
        for _ in $(seq 1 30); do
            if ! kill -0 "$SERVER_PID" 2>/dev/null; then
                break
            fi
            sleep 1
        done
        if kill -0 "$SERVER_PID" 2>/dev/null; then
            printf 'graceful_timeout_force_kill\n' >> "$ARTIFACT_DIR/process-cleanup.txt"
            kill -KILL -- "-$SERVER_PID" 2>/dev/null || cleanup_status=1
        else
            printf 'graceful_termination_confirmed\n' >> "$ARTIFACT_DIR/process-cleanup.txt"
        fi
    else
        printf 'server_already_exited\n' >> "$ARTIFACT_DIR/process-cleanup.txt"
    fi
    wait "$SERVER_PID" 2>/dev/null || true
    remaining=$(ps -eo pid=,pgid=,args= | awk -v group="$SERVER_PID" '$2 == group {print}')
    if [ -n "$remaining" ]; then
        printf 'remaining_server_process_group_members:\n%s\n' "$remaining" >> "$ARTIFACT_DIR/process-cleanup.txt"
        cleanup_status=1
    else
        printf 'no_server_process_remains\n' >> "$ARTIFACT_DIR/process-cleanup.txt"
    fi
    SERVER_CLEANUP_COMPLETE=1
    return "$cleanup_status"
}

record_agent_cleanup() {
    local remaining=
    remaining=$(ps -eo pid=,args= | awk -v root="$WORK_ROOT" 'index($0, root) && $0 !~ /awk -v root/ {print}')
    if [ -n "$remaining" ]; then
        printf 'remaining_agent_processes:\n%s\n' "$remaining" >> "$ARTIFACT_DIR/process-cleanup.txt"
        return 1
    fi
    printf 'no_agent_process_remains\n' >> "$ARTIFACT_DIR/process-cleanup.txt"
}

finalize_result() {
    local script_status=$1
    "$AGENT_ENV/bin/python" "$PROJECT/scripts/mini_swe_smoke_evidence.py" finalize \
        --artifact-dir "$ARTIFACT_DIR" \
        --slurm-exit-status "$script_status" \
        --agent-process-exit "$AGENT_PROCESS_EXIT"
}

on_exit() {
    local status=$?
    set +e
    preserve_agent_artifacts
    if [ "$SERVER_CLEANUP_COMPLETE" -ne 1 ]; then
        terminate_server || status=1
    fi
    nvidia-smi > "$ARTIFACT_DIR/nvidia-smi-after.txt" 2>&1 || status=1
    record_agent_cleanup || status=1
    printf 'job_finished_at=%s\n' "$(date --iso-8601=seconds)" >> "$ARTIFACT_DIR/timestamps.txt"
    printf 'job_exit_status=%s\n' "$status" >> "$ARTIFACT_DIR/timestamps.txt"
    if [ "$RESULT_FINALIZED" -ne 1 ]; then
        finalize_result "$status" || status=1
    fi
    trap - EXIT
    exit "$status"
}
trap on_exit EXIT

hostname -f > "$ARTIFACT_DIR/hostname.txt"
git -C "$PROJECT" rev-parse HEAD > "$ARTIFACT_DIR/git-commit.txt"
git -C "$PROJECT" --no-pager status --short --branch > "$ARTIFACT_DIR/project-git-status.txt"
env | grep '^SLURM_' | sort > "$ARTIFACT_DIR/slurm-environment.txt"

# shellcheck disable=SC1091
source "$PROJECT/scripts/vllm_smoke_batch_bootstrap.sh"
if vllm_smoke_bootstrap "$ARTIFACT_DIR" "$VLLM_ENV"; then
    :
else
    bootstrap_status=$?
    printf 'bootstrap_exit_status=%s\n' "$bootstrap_status" >> "$ARTIFACT_DIR/batch-shell-preflight.txt"
    exit "$bootstrap_status"
fi

export HF_HOME=/home/s224049759/model-cache/huggingface
export HF_HUB_DISABLE_TELEMETRY=1
export TOKENIZERS_PARALLELISM=false
export PYTHONNOUSERSITE=1
export NO_PROXY=127.0.0.1,localhost
export no_proxy=127.0.0.1,localhost

"$VLLM_ENV/bin/python" "$PROJECT/scripts/check_vllm_guided_decoding_deps.py" \
    > "$ARTIFACT_DIR/guided-decoding-dependency-check.txt" 2>&1
"$VLLM_ENV/bin/python" -m pip freeze | sort > "$ARTIFACT_DIR/pip-freeze-vllm.txt"
"$UV" pip check --python "$AGENT_ENV/bin/python" > "$ARTIFACT_DIR/agent-environment-check.txt" 2>&1
"$UV" pip freeze --python "$AGENT_ENV/bin/python" | sort > "$ARTIFACT_DIR/pip-freeze-agent.txt"
"$AGENT_ENV/bin/python" -c "from importlib.metadata import version; print(version('mini-swe-agent'))" \
    > "$ARTIFACT_DIR/agent-version.txt"

printf 'served_model=%s\nrevision=%s\nbase_url=http://127.0.0.1:8000/v1\ndtype=bfloat16\nmax_model_len=4096\ngpu_memory_utilization=0.70\nguided_decoding_backend=lm-format-enforcer\n' \
    "$MODEL" "$REVISION" > "$ARTIFACT_DIR/model-config.txt"
printf '%q ' vllm serve "$MODEL" --revision "$REVISION" --host 127.0.0.1 --port 8000 \
    --dtype bfloat16 --max-model-len 4096 --gpu-memory-utilization 0.70 \
    --guided-decoding-backend lm-format-enforcer > "$ARTIFACT_DIR/server-command.txt"
printf '\n' >> "$ARTIFACT_DIR/server-command.txt"

nvidia-smi > "$ARTIFACT_DIR/nvidia-smi-before.txt"
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits > "$ARTIFACT_DIR/gpu-info.txt"
nvidia-smi topo -m > "$ARTIFACT_DIR/nvidia-smi-topology.txt"

server_launch_epoch=$("$VLLM_ENV/bin/python" -c 'import time; print(time.time())')
printf 'server_launch_at=%s\n' "$(date --iso-8601=seconds)" >> "$ARTIFACT_DIR/timestamps.txt"
setsid "$VLLM_ENV/bin/vllm" serve "$MODEL" \
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

"$AGENT_ENV/bin/python" "$PROJECT/scripts/mini_swe_smoke_evidence.py" probe \
    --artifact-dir "$ARTIFACT_DIR" \
    --server-pid "$SERVER_PID" \
    --server-launch-epoch "$server_launch_epoch" \
    --base-url http://127.0.0.1:8000 \
    --model-id "$MODEL" \
    --startup-timeout 180 \
    > "$ARTIFACT_DIR/server-probe.stdout.log" \
    2> "$ARTIFACT_DIR/server-probe.stderr.log"

export PATH="$HARNESS_ENV/bin:$PATH"
printf 'agent_launch_at=%s\n' "$(date --iso-8601=seconds)" >> "$ARTIFACT_DIR/timestamps.txt"
set +e
PYTHONPATH="$PROJECT/src:$PROJECT" "$HARNESS_ENV/bin/python" -m cmpilot smoke \
    --live \
    --base-url http://127.0.0.1:8000/v1 \
    --model "$MODEL" \
    --mini-python "$AGENT_ENV/bin/python" \
    --runs-root "$INNER_RUNS" \
    --agent-timeout 480 \
    > "$ARTIFACT_DIR/harness.stdout.log" \
    2> "$ARTIFACT_DIR/harness.stderr.log"
AGENT_PROCESS_EXIT=$?
set -e
printf 'agent_process_exit_status=%s\n' "$AGENT_PROCESS_EXIT" >> "$ARTIFACT_DIR/timestamps.txt"
printf 'agent_finished_at=%s\n' "$(date --iso-8601=seconds)" >> "$ARTIFACT_DIR/timestamps.txt"

preserve_agent_artifacts
terminate_server
nvidia-smi > "$ARTIFACT_DIR/nvidia-smi-after.txt"
record_agent_cleanup
printf 'server_cleanup_finished_at=%s\n' "$(date --iso-8601=seconds)" >> "$ARTIFACT_DIR/timestamps.txt"

set +e
finalize_result "$AGENT_PROCESS_EXIT"
FINAL_STATUS=$?
set -e
RESULT_FINALIZED=1
exit "$FINAL_STATUS"
