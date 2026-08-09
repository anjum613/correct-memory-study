#!/usr/bin/bash
#SBATCH --job-name=qwen36-p01-interval-merge
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=192G
#SBATCH --gres=gpu:a100:2
#SBATCH --time=03:00:00
#SBATCH --no-requeue
#SBATCH --output=/home/s224049759/slurm-logs/qwen36-p01-interval-merge-%j.out
#SBATCH --error=/home/s224049759/slurm-logs/qwen36-p01-interval-merge-%j.err

set -euo pipefail

PROJECT=/home/s224049759/projects/worktrees/qwen32b-protocol-hardening
CMPILOT_PY=/home/s224049759/environments/cmpilot-conda/bin/python
MINI_PY=/home/s224049759/environments/mini-swe-agent-smoke/bin/python
VLLM_PY=/home/s224049759/environments/qwen36-vllm-v1/bin/python
MODEL_ID=Qwen/Qwen3.6-27B
MODEL_REVISION=6a9e13bd6fc8f0983b9b99948120bc37f49c13e9
MODEL=/home/s224049759/model-cache/huggingface/hub/models--Qwen--Qwen3.6-27B/snapshots/$MODEL_REVISION
MODEL_CACHE=/home/s224049759/model-cache/huggingface
TASK_ID=qnm-p01-interval-merge
TASK_SEED=1602021252
TASK_ROLE=primary

SUITE=$PROJECT/qualification/qwen32b-v1/suite-manifest.json
SUITE_REFERENCE=$PROJECT/qualification/qwen36-v1/suite-reference.json
TASK=$PROJECT/qualification/qwen32b-v1/tasks/$TASK_ID.json
FREEZE=$PROJECT/qualification/qwen36-v1/qualification-freeze-manifest.json
EXPECTED_FREEZE_SHA256=7c8e22bcdd6d2e264ed205310b584df3643e5499e01e354b71779fc3fdcfca91
CPU_GATE=/home/s224049759/run-artifacts/qwen36-no-memory-qualification/v1/cpu-preflight-qualification-port-fix-25953-v2/cpu-preflight-result.json
ENV_FINGERPRINT=$PROJECT/qualification/qwen36-v1/environment-fingerprint.json
ENV_CONTENT=$PROJECT/qualification/qwen36-v1/environment-content-digest.json
ARTIFACT_ROOT=/home/s224049759/run-artifacts/qwen36-no-memory-qualification/v1/tasks/$TASK_ID/jobs
ARTIFACT_DIR=$ARTIFACT_ROOT/$SLURM_JOB_ID
RUN_ARTIFACT=$ARTIFACT_DIR/run
RUNTIME_SCRATCH=/tmp/cmq-$SLURM_JOB_ID
PORT_HELPER=$PROJECT/scripts/qwen36_server_port.py
MAX_SERVER_BIND_ATTEMPTS=4
PORT_LOCK_ROOT=/tmp/cmq-qwen36-$UID-ports
PORT=
BASE_URL=
PORT_LOCK_FD=
PORT_LOCK_FILE=
SERVER_PID=

mkdir -p "$ARTIFACT_DIR"

cleanup_server() {
    local cleanup_status=0
    if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
        kill -TERM -- "-$SERVER_PID" 2>/dev/null || cleanup_status=1
        for _ in $(seq 1 30); do
            if ! kill -0 "$SERVER_PID" 2>/dev/null; then break; fi
            sleep 1
        done
        if kill -0 "$SERVER_PID" 2>/dev/null; then
            kill -KILL -- "-$SERVER_PID" 2>/dev/null || cleanup_status=1
        fi
    fi
    if [ -n "$SERVER_PID" ]; then wait "$SERVER_PID" 2>/dev/null || true; fi
    return "$cleanup_status"
}

release_port_claim() {
    local release_status=0
    if [ -n "$PORT_LOCK_FD" ]; then
        if [ -n "$PORT_LOCK_FILE" ]; then
            /usr/bin/rm -f -- "$PORT_LOCK_FILE" || release_status=1
        fi
        exec {PORT_LOCK_FD}>&- || release_status=1
    fi
    PORT_LOCK_FD=
    PORT_LOCK_FILE=
    return "$release_status"
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
    cleanup_server || status=1
    release_port_claim || status=1
    cleanup_scratch || status=1
    /usr/bin/nvidia-smi > "$ARTIFACT_DIR/nvidia-smi-final.txt" 2>&1 || status=1
    printf '%s\n' "$status" > "$ARTIFACT_DIR/job-exit-code.txt"
    printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$ARTIFACT_DIR/job-finished-utc.txt"
    "$CMPILOT_PY" "$PROJECT/scripts/qualification_job_manifest.py" "$ARTIFACT_DIR" || status=1
    trap - EXIT
    exit "$status"
}
trap on_exit EXIT

test -x "$CMPILOT_PY"
test -x "$MINI_PY"
test -x "$VLLM_PY"
test -d "$MODEL"
test -f "$CPU_GATE"
test -f "$SUITE"
test -f "$SUITE_REFERENCE"
test -f "$TASK"
test -f "$FREEZE"
test "$(sha256sum "$FREEZE" | cut -d' ' -f1)" = "$EXPECTED_FREEZE_SHA256"

"$CMPILOT_PY" - "$CPU_GATE" "$TASK_ID" "$TASK_SEED" <<'PY'
import json
import sys
from pathlib import Path
record = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if record.get("overall") != "PASS" or not all(record.get("checks", {}).values()):
    raise SystemExit("Qwen3.6 post-freeze CPU gate is not PASS")
if record.get("seeds", {}).get(sys.argv[2]) != int(sys.argv[3]):
    raise SystemExit("task seed differs from CPU-gated schedule")
PY

git -C "$PROJECT" rev-parse HEAD > "$ARTIFACT_DIR/project-commit.txt"
git -C "$PROJECT" status --porcelain > "$ARTIFACT_DIR/project-status.txt"
test ! -s "$ARTIFACT_DIR/project-status.txt"
git -C "$PROJECT" rev-list -n 1 qwen32b-qualification-v1 > "$ARTIFACT_DIR/qwen32b-freeze-tag-target.txt"
test "$(sed -n '1p' "$ARTIFACT_DIR/qwen32b-freeze-tag-target.txt")" = ba039a0eaddc358d6b7174260c3b3c36169c44c0
sha256sum "$0" "$SUITE" "$SUITE_REFERENCE" "$TASK" "$FREEZE" \
    "$PROJECT/qualification/qwen36-v1/qualification-agent-config.json" \
    "$PROJECT/qualification/qwen36-v1/qualification-seeds.json" \
    "$PORT_HELPER" \
    > "$ARTIFACT_DIR/runtime-input-hashes.txt"
printf '%s\n' "$TASK_ID" > "$ARTIFACT_DIR/task-id.txt"
printf '%s\n' "$TASK_ROLE" > "$ARTIFACT_DIR/task-role.txt"
printf '%s\n' "$TASK_SEED" > "$ARTIFACT_DIR/task-seed.txt"

printf '%s\n' "$MODEL_ID" > "$ARTIFACT_DIR/model-id.txt"
printf '%s\n' "$MODEL_REVISION" > "$ARTIFACT_DIR/model-revision.txt"
printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$ARTIFACT_DIR/job-started-utc.txt"
hostname > "$ARTIFACT_DIR/hostname.txt"
env | grep '^SLURM_' | LC_ALL=C sort > "$ARTIFACT_DIR/slurm-environment.txt"
/usr/bin/nvidia-smi > "$ARTIFACT_DIR/nvidia-smi-initial.txt"
/usr/bin/nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader,nounits \
    > "$ARTIFACT_DIR/gpu-allocation.csv"

export HF_HOME="$MODEL_CACHE"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_HUB_DISABLE_TELEMETRY=1
export TOKENIZERS_PARALLELISM=false
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export NO_PROXY=127.0.0.1,localhost
export no_proxy=127.0.0.1,localhost

"$CMPILOT_PY" "$PROJECT/scripts/qualification_runtime_path.py" validate \
    --job-id "$SLURM_JOB_ID" \
    --task-id "$TASK_ID" \
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
printf 'TMPDIR=%s\nTEMP=%s\nTMP=%s\nVLLM_RPC_BASE_PATH=%s\n' \
    "$TMPDIR" "$TEMP" "$TMP" "$VLLM_RPC_BASE_PATH" \
    > "$ARTIFACT_DIR/runtime-environment.txt"

"$VLLM_PY" "$PROJECT/scripts/verify_qwen36_environment.py" \
    --output-directory "$ARTIFACT_DIR/environment-verification" \
    --expected-fingerprint "$ENV_FINGERPRINT" \
    --expected-content "$ENV_CONTENT" \
    > "$ARTIFACT_DIR/environment-verification.stdout" \
    2> "$ARTIFACT_DIR/environment-verification.stderr"

"$CMPILOT_PY" "$PORT_HELPER" schedule \
    --job-id "$SLURM_JOB_ID" \
    --record "$ARTIFACT_DIR/server-port-schedule.json" \
    > "$ARTIFACT_DIR/server-port-helper.stdout"
: > "$ARTIFACT_DIR/server-port-attempts.jsonl"
/usr/bin/install -d -m 700 "$PORT_LOCK_ROOT"

server_selected=0
for attempt in $(seq 1 "$MAX_SERVER_BIND_ATTEMPTS"); do
    PORT=$("$CMPILOT_PY" "$PORT_HELPER" candidate \
        --job-id "$SLURM_JOB_ID" --attempt "$attempt")
    BASE_URL=http://127.0.0.1:$PORT
    PORT_LOCK_FILE=$PORT_LOCK_ROOT/$PORT.lock
    exec {candidate_lock_fd}> "$PORT_LOCK_FILE"
    if ! /usr/bin/flock --exclusive --nonblock "$candidate_lock_fd"; then
        exec {candidate_lock_fd}>&-
        PORT_LOCK_FILE=
        "$CMPILOT_PY" "$PORT_HELPER" record-attempt \
            --record "$ARTIFACT_DIR/server-port-attempts.jsonl" \
            --job-id "$SLURM_JOB_ID" --attempt "$attempt" --port "$PORT" \
            --outcome ACTIVE_ENDPOINT_CLAIM_RETRY \
            >> "$ARTIFACT_DIR/server-port-helper.stdout"
        continue
    fi
    PORT_LOCK_FD=$candidate_lock_fd
    printf '%q ' "$VLLM_PY" -m vllm.entrypoints.openai.api_server \
        --host 127.0.0.1 --port "$PORT" --model "$MODEL" --tokenizer "$MODEL" \
        --served-model-name "$MODEL_ID" --dtype bfloat16 --tensor-parallel-size 2 \
        --max-model-len 32768 --max-num-seqs 1 --gpu-memory-utilization 0.90 \
        --seed "$TASK_SEED" --enforce-eager --reasoning-parser qwen3 \
        --language-model-only --generation-config vllm \
        > "$ARTIFACT_DIR/server-command.txt"
    printf '\n' >> "$ARTIFACT_DIR/server-command.txt"

    : > "$ARTIFACT_DIR/server.stdout"
    : > "$ARTIFACT_DIR/server.stderr"
    setsid "$VLLM_PY" -m vllm.entrypoints.openai.api_server \
        --host 127.0.0.1 \
        --port "$PORT" \
        --model "$MODEL" \
        --tokenizer "$MODEL" \
        --served-model-name "$MODEL_ID" \
        --dtype bfloat16 \
        --tensor-parallel-size 2 \
        --max-model-len 32768 \
        --max-num-seqs 1 \
        --gpu-memory-utilization 0.90 \
        --seed "$TASK_SEED" \
        --enforce-eager \
        --reasoning-parser qwen3 \
        --language-model-only \
        --generation-config vllm \
        > "$ARTIFACT_DIR/server.stdout" \
        2> "$ARTIFACT_DIR/server.stderr" &
    SERVER_PID=$!
    printf '%s\n' "$SERVER_PID" > "$ARTIFACT_DIR/server.pid"

    ready=0
    bind_collision=0
    for _ in $(seq 1 360); do
        if ! kill -0 "$SERVER_PID" 2>/dev/null; then
            set +e
            wait "$SERVER_PID"
            server_status=$?
            set -e
            SERVER_PID=
            if "$CMPILOT_PY" "$PORT_HELPER" classify-bind-failure \
                --stderr "$ARTIFACT_DIR/server.stderr" \
                --exit-code "$server_status" \
                --record "$ARTIFACT_DIR/server-bind-classification-$attempt.json" \
                >> "$ARTIFACT_DIR/server-port-helper.stdout"; then
                cp "$ARTIFACT_DIR/server-command.txt" \
                    "$ARTIFACT_DIR/server-bind-attempt-$attempt.command.txt"
                cp "$ARTIFACT_DIR/server.stdout" \
                    "$ARTIFACT_DIR/server-bind-attempt-$attempt.stdout"
                cp "$ARTIFACT_DIR/server.stderr" \
                    "$ARTIFACT_DIR/server-bind-attempt-$attempt.stderr"
                "$CMPILOT_PY" "$PORT_HELPER" record-attempt \
                    --record "$ARTIFACT_DIR/server-port-attempts.jsonl" \
                    --job-id "$SLURM_JOB_ID" --attempt "$attempt" --port "$PORT" \
                    --outcome EADDRINUSE_RETRY --server-exit-code "$server_status" \
                    >> "$ARTIFACT_DIR/server-port-helper.stdout"
                release_port_claim
                bind_collision=1
                break
            fi
            "$CMPILOT_PY" "$PORT_HELPER" record-attempt \
                --record "$ARTIFACT_DIR/server-port-attempts.jsonl" \
                --job-id "$SLURM_JOB_ID" --attempt "$attempt" --port "$PORT" \
                --outcome FATAL_SERVER_EXIT --server-exit-code "$server_status" \
                >> "$ARTIFACT_DIR/server-port-helper.stdout"
            if [ "$server_status" -eq 0 ]; then server_status=1; fi
            exit "$server_status"
        fi
        status=$(/usr/bin/curl --noproxy '*' --silent \
            --output "$ARTIFACT_DIR/health-response.raw" \
            --write-out '%{http_code}' "$BASE_URL/health" || true)
        if [ "$status" = 200 ]; then
            ready=1
            server_selected=1
            printf '%s\n' "$PORT" > "$ARTIFACT_DIR/selected-server-port.txt"
            printf '%s\n' "$BASE_URL" > "$ARTIFACT_DIR/server-base-url.txt"
            "$CMPILOT_PY" "$PORT_HELPER" record-attempt \
                --record "$ARTIFACT_DIR/server-port-attempts.jsonl" \
                --job-id "$SLURM_JOB_ID" --attempt "$attempt" --port "$PORT" \
                --outcome SERVER_READY \
                >> "$ARTIFACT_DIR/server-port-helper.stdout"
            break
        fi
        sleep 1
    done
    if [ "$server_selected" -eq 1 ]; then break; fi
    if [ "$bind_collision" -eq 1 ]; then continue; fi
    "$CMPILOT_PY" "$PORT_HELPER" record-attempt \
        --record "$ARTIFACT_DIR/server-port-attempts.jsonl" \
        --job-id "$SLURM_JOB_ID" --attempt "$attempt" --port "$PORT" \
        --outcome HEALTH_TIMEOUT \
        >> "$ARTIFACT_DIR/server-port-helper.stdout"
    exit 1
done
printf '%s\n' "$server_selected" > "$ARTIFACT_DIR/server-ready.txt"
test "$server_selected" -eq 1
/usr/bin/curl --noproxy '*' --silent --show-error "$BASE_URL/v1/models" \
    > "$ARTIFACT_DIR/models-response.json"

set +e
"$CMPILOT_PY" "$PROJECT/scripts/run_qualification_task.py" \
    --project-root "$PROJECT" \
    --suite-manifest "$SUITE" \
    --suite-reference "$SUITE_REFERENCE" \
    --task-manifest "$TASK" \
    --freeze-manifest "$FREEZE" \
    --artifact-directory "$RUN_ARTIFACT" \
    --base-url "$BASE_URL/v1" \
    --model "$MODEL_ID" \
    --tokenizer-path "$MODEL" \
    --mini-python "$MINI_PY" \
    --seed "$TASK_SEED" \
    --agent-timeout 600 \
    --server-pid "$SERVER_PID" \
    --runtime-integrity "$ARTIFACT_DIR/environment-verification/result.json" \
    > "$ARTIFACT_DIR/qualification-runner.stdout" \
    2> "$ARTIFACT_DIR/qualification-runner.stderr"
runner_status=$?
set -e
printf '%s\n' "$runner_status" > "$ARTIFACT_DIR/qualification-runner.exit"
wait "$SERVER_PID" 2>/dev/null || true
SERVER_PID=
test "$runner_status" -eq 0
