#!/usr/bin/bash
#SBATCH --job-name=devstral-small-2507-smoke-v1
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
#SBATCH --gres=gpu:a100:2
#SBATCH --time=01:00:00
#SBATCH --no-requeue
#SBATCH --output=/home/s224049759/slurm-logs/devstral-small-2507-smoke-v1-%j.out
#SBATCH --error=/home/s224049759/slurm-logs/devstral-small-2507-smoke-v1-%j.err

set -euo pipefail
umask 077

PROJECT=/home/s224049759/projects/worktrees/final-six-family-experiment
CMPILOT_PY=/home/s224049759/environments/cmpilot-conda/bin/python
SERVER_PY=/home/s224049759/environments/devstral-small-2507-v1/bin/python
MINI_PY=/home/s224049759/environments/devstral-small-2507-agent-v1/bin/python
MODEL_ID=mistralai/Devstral-Small-2507
MODEL_REVISION=bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39
MODEL=/home/s224049759/model-cache/huggingface/hub/models--mistralai--Devstral-Small-2507/snapshots/$MODEL_REVISION
MODEL_CACHE=/home/s224049759/model-cache/huggingface
ARTIFACT_ROOT=/home/s224049759/final-experiment-artifacts/devstral-small-2507-technical-smoke/v1/jobs
ARTIFACT_DIR="$ARTIFACT_ROOT/$SLURM_JOB_ID"
RUNS_ROOT="$ARTIFACT_DIR/runs"
PORT=49827
BASE_URL="http://127.0.0.1:$PORT"
AGENT_CONFIG="$PROJECT/configs/agent/mini_swe_agent_smoke.yaml"
SERVER_PID=
GPU_MONITOR_PID=
RUNNER_STATUS=125
FINALIZED=0

mkdir -p "$ARTIFACT_ROOT"
if [ -e "$ARTIFACT_DIR" ] || [ -L "$ARTIFACT_DIR" ]; then
    printf 'refusing to overwrite smoke artifact: %s\n' "$ARTIFACT_DIR" >&2
    exit 1
fi
mkdir "$ARTIFACT_DIR"

stop_gpu_monitor() {
    if [ -n "$GPU_MONITOR_PID" ]; then
        kill -TERM "$GPU_MONITOR_PID" 2>/dev/null || true
        wait "$GPU_MONITOR_PID" 2>/dev/null || true
        GPU_MONITOR_PID=
    fi
}

cleanup_server() {
    local cleanup_status=0
    local observed_exit=not-started
    local process_state=
    if [ -f "$ARTIFACT_DIR/server-cleanup.json" ]; then
        return 0
    fi
    if [ -n "$SERVER_PID" ]; then
        process_state=$(/usr/bin/ps -o stat= -p "$SERVER_PID" 2>/dev/null || true)
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
    printf '{"cleanup_status":%s,"observed_exit":"%s","pass":%s,"schema":"devstral-technical-smoke-clean-shutdown-v1"}\n' \
        "$cleanup_status" "$observed_exit" \
        "$([ "$cleanup_status" -eq 0 ] && printf true || printf false)" \
        > "$ARTIFACT_DIR/server-cleanup.json"
    SERVER_PID=
    return "$cleanup_status"
}

on_exit() {
    local status=$?
    set +e
    stop_gpu_monitor
    cleanup_server || status=1
    /usr/bin/nvidia-smi --query-gpu=index,name,memory.used \
        --format=csv,noheader,nounits > "$ARTIFACT_DIR/gpu-memory-after-shutdown.csv" 2>&1 || status=1
    if [ "$FINALIZED" -ne 1 ]; then
        "$CMPILOT_PY" "$PROJECT/scripts/devstral_technical_smoke.py" finalize \
            --artifact-directory "$ARTIFACT_DIR" \
            --runner-exit-code "$RUNNER_STATUS" \
            > "$ARTIFACT_DIR/emergency-finalization.stdout" \
            2> "$ARTIFACT_DIR/emergency-finalization.stderr" || true
    fi
    printf '%s\n' "$status" > "$ARTIFACT_DIR/job-exit-code.txt"
    date -u +%Y-%m-%dT%H:%M:%SZ > "$ARTIFACT_DIR/job-finished-utc.txt"
    "$CMPILOT_PY" "$PROJECT/scripts/qualification_job_manifest.py" \
        "$ARTIFACT_DIR" || status=1
    trap - EXIT
    exit "$status"
}
trap on_exit EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

test -x "$CMPILOT_PY"
test -x "$SERVER_PY"
test -x "$MINI_PY"
test -d "$MODEL"
test -f "$MODEL/consolidated.safetensors"
test -f "$AGENT_CONFIG"

git -C "$PROJECT" rev-parse HEAD > "$ARTIFACT_DIR/project-commit.txt"
git -C "$PROJECT" status --porcelain > "$ARTIFACT_DIR/project-status.txt"
test ! -s "$ARTIFACT_DIR/project-status.txt"
printf '%s\n' false > "$ARTIFACT_DIR/confirmatory.txt"
printf '%s\n' false > "$ARTIFACT_DIR/scientific-evidence.txt"
printf '%s\n' calculator-engineering-smoke > "$ARTIFACT_DIR/fixture-id.txt"
hostname > "$ARTIFACT_DIR/hostname.txt"
date -u +%Y-%m-%dT%H:%M:%SZ > "$ARTIFACT_DIR/job-started-utc.txt"
env | awk -F= '$1 ~ /^SLURM_/ {print}' | LC_ALL=C sort \
    > "$ARTIFACT_DIR/slurm-environment.txt"
sha256sum "$0" "$PROJECT/qualification/devstral-small-2507-snapshot-freeze.json" \
    "$AGENT_CONFIG" > "$ARTIFACT_DIR/runtime-input-hashes.txt"

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

"$SERVER_PY" "$PROJECT/scripts/verify_devstral_environment.py" \
    > "$ARTIFACT_DIR/environment-verification.json" \
    2> "$ARTIFACT_DIR/environment-verification.stderr"
"$CMPILOT_PY" "$PROJECT/scripts/devstral_technical_smoke.py" preflight \
    --verification "$ARTIFACT_DIR/environment-verification.json" \
    --output-directory "$ARTIFACT_DIR" \
    > "$ARTIFACT_DIR/preflight.stdout" \
    2> "$ARTIFACT_DIR/preflight.stderr"
"$CMPILOT_PY" "$PROJECT/scripts/extract_server_command.py" \
    --command-json "$ARTIFACT_DIR/server-command.json" \
    --result "$ARTIFACT_DIR/server-command-extraction.json" \
    > "$ARTIFACT_DIR/server-command.nul"
mapfile -d '' -t SERVER_COMMAND < "$ARTIFACT_DIR/server-command.nul"
test "${#SERVER_COMMAND[@]}" -gt 20
test -x "${SERVER_COMMAND[0]}"
printf '%q ' "${SERVER_COMMAND[@]}" > "$ARTIFACT_DIR/server-command.txt"
printf '\n' >> "$ARTIFACT_DIR/server-command.txt"

/usr/bin/nvidia-smi --query-gpu=index,name,uuid,memory.total,memory.used,memory.free \
    --format=csv,noheader,nounits > "$ARTIFACT_DIR/gpu-allocation.csv"
test "$(wc -l < "$ARTIFACT_DIR/gpu-allocation.csv")" -eq 2
test "$(awk -F, 'index($2, "A100") {count++} END {print count+0}' "$ARTIFACT_DIR/gpu-allocation.csv")" -eq 2
/usr/bin/nvidia-smi topo -m > "$ARTIFACT_DIR/gpu-topology.txt"

(
    while true; do
        /usr/bin/nvidia-smi --query-gpu=index,name,memory.used \
            --format=csv,noheader,nounits >> "$ARTIFACT_DIR/gpu-memory-samples.csv" || exit
        sleep 2
    done
) &
GPU_MONITOR_PID=$!

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
for _ in $(seq 1 900); do
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
"$CMPILOT_PY" - "$ARTIFACT_DIR/models-response.json" "$MODEL_ID" <<'PY'
import json
import sys
from pathlib import Path

value = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
models = [row.get("id") for row in value.get("data", []) if isinstance(row, dict)]
if sys.argv[2] not in models:
    raise SystemExit(f"served model identity mismatch: {models}")
PY

"$CMPILOT_PY" "$PROJECT/scripts/devstral_technical_smoke.py" authorization-probe \
    --output "$ARTIFACT_DIR/authorization-probe.json" \
    > "$ARTIFACT_DIR/authorization-probe.stdout" \
    2> "$ARTIFACT_DIR/authorization-probe.stderr"

set +e
"$CMPILOT_PY" "$PROJECT/scripts/run_devstral_calculator_smoke.py" \
    --base-url "$BASE_URL/v1" \
    --runs-root "$RUNS_ROOT" \
    --runtime-integrity "$ARTIFACT_DIR/runtime-integrity.json" \
    --agent-config-source "$AGENT_CONFIG" \
    --agent-timeout 600 \
    > "$ARTIFACT_DIR/calculator-runner.stdout" \
    2> "$ARTIFACT_DIR/calculator-runner.stderr"
RUNNER_STATUS=$?
set -e
printf '%s\n' "$RUNNER_STATUS" > "$ARTIFACT_DIR/calculator-runner.exit"

stop_gpu_monitor
cleanup_server
/usr/bin/nvidia-smi --query-gpu=index,name,uuid,memory.total,memory.used,memory.free \
    --format=csv,noheader,nounits > "$ARTIFACT_DIR/gpu-memory-after-shutdown.csv"

set +e
"$CMPILOT_PY" "$PROJECT/scripts/devstral_technical_smoke.py" complete \
    --artifact-directory "$ARTIFACT_DIR" \
    --runner-exit-code "$RUNNER_STATUS" \
    --output "$ARTIFACT_DIR/technical-smoke-result.json" \
    > "$ARTIFACT_DIR/completion.stdout" \
    2> "$ARTIFACT_DIR/completion.stderr"
SMOKE_STATUS=$?
set -e
FINALIZED=1
exit "$SMOKE_STATUS"
