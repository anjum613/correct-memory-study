#!/usr/bin/bash
#SBATCH --job-name=qwen32b-final-smoke-v2
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
#SBATCH --gres=gpu:a100:2
#SBATCH --time=00:30:00
#SBATCH --no-requeue
#SBATCH --output=/home/s224049759/slurm-logs/qwen32b-final-smoke-v2-%j.out
#SBATCH --error=/home/s224049759/slurm-logs/qwen32b-final-smoke-v2-%j.err

set -euo pipefail
umask 077

PROJECT=/home/s224049759/projects/worktrees/final-six-family-experiment
CMPILOT_PY=/home/s224049759/environments/cmpilot-conda/bin/python
MINI_PY=/home/s224049759/environments/mini-swe-agent-smoke/bin/python
MODEL=/home/s224049759/model-cache/huggingface/hub/models--Qwen--Qwen2.5-Coder-32B-Instruct/snapshots/381fc969f78efac66bc87ff7ddeadb7e73c218a7
MODEL_CACHE=/home/s224049759/model-cache/huggingface
ARTIFACT_ROOT=/home/s224049759/final-experiment-artifacts/qwen32b-final-technical-smoke/v2/jobs
ARTIFACT_DIR="$ARTIFACT_ROOT/$SLURM_JOB_ID"
RUN_ARTIFACT="$ARTIFACT_DIR/run"
RUNTIME_SCRATCH="/tmp/cmq-$SLURM_JOB_ID"
SUITE="$PROJECT/qualification/qwen32b-v1/suite-manifest.json"
TASK="$PROJECT/qualification/qwen32b-v1/tasks/qnm-p01-interval-merge.json"
FREEZE="$PROJECT/qualification/qwen32b-v1/freeze-manifest.json"
AGENT_CONFIG="$PROJECT/configs/agent/mini_swe_agent_smoke.yaml"
PORT=49788
BASE_URL="http://127.0.0.1:$PORT"
SERVER_PID=

mkdir -p "$ARTIFACT_ROOT"
if [ -e "$ARTIFACT_DIR" ] || [ -L "$ARTIFACT_DIR" ]; then
    printf 'refusing to overwrite smoke artifact: %s\n' "$ARTIFACT_DIR" >&2
    exit 1
fi
mkdir "$ARTIFACT_DIR"

cleanup_server() {
    local cleanup_status=0
    local observed_exit=not-started
    local process_state=
    if [ -n "$SERVER_PID" ]; then
        if ! process_state=$(/usr/bin/ps -o stat= -p "$SERVER_PID" 2>/dev/null); then
            process_state=
        fi
        process_state=${process_state:0:1}
    fi
    if [ "$process_state" = Z ]; then
        observed_exit=already-exited
    elif [ -n "$process_state" ]; then
        observed_exit=terminated
        kill -TERM -- "-$SERVER_PID" 2>/dev/null || cleanup_status=1
        for _ in $(seq 1 30); do
            if ! kill -0 "$SERVER_PID" 2>/dev/null; then
                break
            fi
            sleep 1
        done
        if kill -0 "$SERVER_PID" 2>/dev/null; then
            observed_exit=killed-after-timeout
            kill -KILL -- "-$SERVER_PID" 2>/dev/null || cleanup_status=1
        fi
    elif [ -n "$SERVER_PID" ]; then
        observed_exit=already-exited
    fi
    if [ -n "$SERVER_PID" ]; then
        wait "$SERVER_PID" 2>/dev/null || true
    fi
    printf '{"cleanup_status":%s,"observed_exit":"%s","pass":%s,"schema":"qwen32b-final-smoke-clean-shutdown-v2"}\n' \
        "$cleanup_status" "$observed_exit" \
        "$([ "$cleanup_status" -eq 0 ] && printf true || printf false)" \
        > "$ARTIFACT_DIR/server-cleanup.json"
    SERVER_PID=
    return "$cleanup_status"
}

cleanup_scratch() {
    "$CMPILOT_PY" "$PROJECT/scripts/qualification_runtime_path.py" cleanup \
        --job-id "$SLURM_JOB_ID" \
        --runtime-path "$RUNTIME_SCRATCH" \
        --record "$ARTIFACT_DIR/runtime-scratch-cleanup.json"
}

on_exit() {
    local status=$?
    set +e
    if [ -n "$SERVER_PID" ]; then
        cleanup_server || status=1
    fi
    cleanup_scratch || status=1
    /usr/bin/nvidia-smi > "$ARTIFACT_DIR/nvidia-smi-final.txt" 2>&1 || status=1
    printf '%s\n' "$status" > "$ARTIFACT_DIR/job-exit-code.txt"
    date -u +%Y-%m-%dT%H:%M:%SZ > "$ARTIFACT_DIR/job-finished-utc.txt"
    "$CMPILOT_PY" "$PROJECT/scripts/qualification_job_manifest.py" \
        "$ARTIFACT_DIR" || status=1
    trap - EXIT
    exit "$status"
}
trap on_exit EXIT

test -x "$CMPILOT_PY"
test -x "$MINI_PY"
test -d "$MODEL"
test -f "$SUITE"
test -f "$TASK"
test -f "$FREEZE"
test -f "$AGENT_CONFIG"

git -C "$PROJECT" rev-parse HEAD > "$ARTIFACT_DIR/project-commit.txt"
git -C "$PROJECT" status --porcelain > "$ARTIFACT_DIR/project-status.txt"
test ! -s "$ARTIFACT_DIR/project-status.txt"
git -C "$PROJECT" rev-list -n 1 qwen32b-qualification-v1 \
    > "$ARTIFACT_DIR/qwen32b-freeze-tag-target.txt"
test "$(sed -n '1p' "$ARTIFACT_DIR/qwen32b-freeze-tag-target.txt")" \
    = ba039a0eaddc358d6b7174260c3b3c36169c44c0
git -C "$PROJECT" merge-base --is-ancestor \
    ba039a0eaddc358d6b7174260c3b3c36169c44c0 HEAD
sha256sum "$0" "$SUITE" "$TASK" "$FREEZE" "$AGENT_CONFIG" \
    > "$ARTIFACT_DIR/runtime-input-hashes.txt"
printf '%s\n' false > "$ARTIFACT_DIR/confirmatory.txt"
printf '%s\n' false > "$ARTIFACT_DIR/scientific-evidence.txt"
printf '%s\n' qnm-p01-interval-merge > "$ARTIFACT_DIR/fixture-id.txt"
date -u +%Y-%m-%dT%H:%M:%SZ > "$ARTIFACT_DIR/job-started-utc.txt"
hostname > "$ARTIFACT_DIR/hostname.txt"
env | awk -F= '$1 ~ /^SLURM_/ {print}' | LC_ALL=C sort \
    > "$ARTIFACT_DIR/slurm-environment.txt"

"$CMPILOT_PY" "$PROJECT/scripts/qwen32b_final_smoke.py" preflight \
    --project-root "$PROJECT" \
    --output-directory "$ARTIFACT_DIR" \
    --port "$PORT" \
    > "$ARTIFACT_DIR/preflight.stdout" \
    2> "$ARTIFACT_DIR/preflight.stderr"

"$CMPILOT_PY" "$PROJECT/scripts/extract_server_command.py" \
    --command-json "$ARTIFACT_DIR/server-command.json" \
    --result "$ARTIFACT_DIR/server-command-extraction.json" \
    > "$ARTIFACT_DIR/server-command.nul"
mapfile -d '' -t SERVER_COMMAND < "$ARTIFACT_DIR/server-command.nul"
test "${#SERVER_COMMAND[@]}" -eq 28
VLLM_PY="${SERVER_COMMAND[0]}"
test -x "$VLLM_PY"
printf '%q ' "${SERVER_COMMAND[@]}" > "$ARTIFACT_DIR/server-command.txt"
printf '\n' >> "$ARTIFACT_DIR/server-command.txt"

export HF_HOME="$MODEL_CACHE"
export HF_HUB_CACHE="$MODEL_CACHE/hub"
export HF_HUB_DISABLE_IMPLICIT_TOKEN=1
export HF_HUB_DISABLE_TELEMETRY=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export TOKENIZERS_PARALLELISM=false
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export NO_PROXY=127.0.0.1,localhost
export no_proxy=127.0.0.1,localhost
unset HF_TOKEN HUGGING_FACE_HUB_TOKEN

"$CMPILOT_PY" "$PROJECT/scripts/qualification_runtime_path.py" validate \
    --job-id "$SLURM_JOB_ID" \
    --task-id qnm-p01-interval-merge \
    --persistent-artifact-root "$ARTIFACT_ROOT" \
    --runtime-path "$RUNTIME_SCRATCH" \
    --record "$ARTIFACT_DIR/runtime-ipc-path-budget.json"
"$CMPILOT_PY" "$PROJECT/scripts/qualification_runtime_path.py" prepare \
    --job-id "$SLURM_JOB_ID" \
    --runtime-path "$RUNTIME_SCRATCH" \
    --record "$ARTIFACT_DIR/runtime-scratch-preparation.json"
export TMPDIR="$RUNTIME_SCRATCH"
export TEMP="$RUNTIME_SCRATCH"
export TMP="$RUNTIME_SCRATCH"
export VLLM_RPC_BASE_PATH="$RUNTIME_SCRATCH"

"$VLLM_PY" "$PROJECT/scripts/environment_fingerprint.py" capture \
    --inventory "$ARTIFACT_DIR/environment-inventory.json" \
    --record "$ARTIFACT_DIR/environment-fingerprint.json"
"$VLLM_PY" "$PROJECT/scripts/environment_content_digest.py" \
    --inventory "$ARTIFACT_DIR/environment-content-inventory.json" \
    --record "$ARTIFACT_DIR/environment-content-digest.json"
"$CMPILOT_PY" "$PROJECT/scripts/qwen32b_final_smoke.py" runtime-integrity \
    --fingerprint "$ARTIFACT_DIR/environment-fingerprint.json" \
    --content "$ARTIFACT_DIR/environment-content-digest.json" \
    --output "$ARTIFACT_DIR/runtime-integrity.json"

/usr/bin/nvidia-smi > "$ARTIFACT_DIR/nvidia-smi-initial.txt"
/usr/bin/nvidia-smi --query-gpu=index,name,uuid,memory.total,memory.used,memory.free \
    --format=csv,noheader,nounits > "$ARTIFACT_DIR/gpu-memory-initial.csv"

"$CMPILOT_PY" - "$PORT" <<'PY'
import socket
import sys

with socket.socket() as probe:
    probe.bind(("127.0.0.1", int(sys.argv[1])))
PY

server_started=$SECONDS
setsid "${SERVER_COMMAND[@]}" \
    > "$ARTIFACT_DIR/server.stdout" \
    2> "$ARTIFACT_DIR/server.stderr" &
SERVER_PID=$!
printf '%s\n' "$SERVER_PID" > "$ARTIFACT_DIR/server.pid"

health_status=000
for _ in $(seq 1 600); do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        break
    fi
    health_status=$(/usr/bin/curl --noproxy '*' --silent --max-time 2 \
        --output "$ARTIFACT_DIR/health-response.raw" \
        --write-out '%{http_code}' "$BASE_URL/health" || true)
    if [ "$health_status" = 200 ]; then
        break
    fi
    sleep 1
done
printf '%s\n' "$health_status" > "$ARTIFACT_DIR/health-http-status.txt"
printf '%s\n' "$((SECONDS - server_started))" \
    > "$ARTIFACT_DIR/server-startup-seconds.txt"
test "$health_status" = 200
/usr/bin/curl --noproxy '*' --silent --show-error --max-time 10 \
    "$BASE_URL/v1/models" > "$ARTIFACT_DIR/models-response.json"
/usr/bin/nvidia-smi --query-gpu=index,name,uuid,memory.total,memory.used,memory.free \
    --format=csv,noheader,nounits > "$ARTIFACT_DIR/gpu-memory-server-ready.csv"

set +e
"$CMPILOT_PY" "$PROJECT/scripts/run_qualification_task.py" \
    --project-root "$PROJECT" \
    --suite-manifest "$SUITE" \
    --task-manifest "$TASK" \
    --freeze-manifest "$FREEZE" \
    --artifact-directory "$RUN_ARTIFACT" \
    --base-url "$BASE_URL/v1" \
    --model "$MODEL" \
    --mini-python "$MINI_PY" \
    --agent-config-source "$AGENT_CONFIG" \
    --tokenizer-path "$MODEL" \
    --agent-timeout 600 \
    --server-pid "$SERVER_PID" \
    --runtime-integrity "$ARTIFACT_DIR/runtime-integrity.json" \
    > "$ARTIFACT_DIR/qualification-runner.stdout" \
    2> "$ARTIFACT_DIR/qualification-runner.stderr"
RUNNER_STATUS=$?
set -e
printf '%s\n' "$RUNNER_STATUS" > "$ARTIFACT_DIR/qualification-runner.exit"

cleanup_server
/usr/bin/nvidia-smi --query-gpu=index,name,uuid,memory.total,memory.used,memory.free \
    --format=csv,noheader,nounits > "$ARTIFACT_DIR/gpu-memory-after-shutdown.csv"

set +e
"$CMPILOT_PY" "$PROJECT/scripts/qwen32b_final_smoke.py" complete \
    --run-artifact "$RUN_ARTIFACT" \
    --health-status "$ARTIFACT_DIR/health-http-status.txt" \
    --models-response "$ARTIFACT_DIR/models-response.json" \
    --runtime-integrity "$ARTIFACT_DIR/runtime-integrity.json" \
    --server-cleanup "$ARTIFACT_DIR/server-cleanup.json" \
    --runner-exit-code "$RUNNER_STATUS" \
    --output "$ARTIFACT_DIR/technical-smoke-result.json" \
    > "$ARTIFACT_DIR/completion-validation.stdout" \
    2> "$ARTIFACT_DIR/completion-validation.stderr"
SMOKE_STATUS=$?
set -e
exit "$SMOKE_STATUS"
