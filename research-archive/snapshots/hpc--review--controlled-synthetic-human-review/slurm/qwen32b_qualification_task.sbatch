#!/usr/bin/bash
#SBATCH --job-name=qwen32b-qnm-p01-r1
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
#SBATCH --gres=gpu:a100:2
#SBATCH --time=03:00:00
#SBATCH --no-requeue
#SBATCH --output=/home/s224049759/slurm-logs/qwen32b-qnm-p01-r1-%j.out
#SBATCH --error=/home/s224049759/slurm-logs/qwen32b-qnm-p01-r1-%j.err

set -euo pipefail

PROJECT=/home/s224049759/projects/worktrees/qwen32b-protocol-hardening
CMPILOT_PY=/home/s224049759/environments/cmpilot-conda/bin/python
MINI_PY=/home/s224049759/environments/mini-swe-agent-smoke/bin/python
VLLM_PY=/home/s224049759/environments/vllm-smoke/bin/python
MODEL=/home/s224049759/model-cache/huggingface/hub/models--Qwen--Qwen2.5-Coder-32B-Instruct/snapshots/381fc969f78efac66bc87ff7ddeadb7e73c218a7
MODEL_CACHE=/home/s224049759/model-cache/huggingface
JOB_25887=/home/s224049759/run-artifacts/qwen32b-calculator/25887
CPU_GATE=/home/s224049759/run-artifacts/qwen32b-no-memory-qualification/v1/cpu-preflight-ipc-fix-25908/cpu-preflight-result.json
ARTIFACT_ROOT=/home/s224049759/run-artifacts/qwen32b-no-memory-qualification/v1/tasks/qnm-p01-interval-merge/jobs
ARTIFACT_DIR="$ARTIFACT_ROOT/$SLURM_JOB_ID"
RUN_ARTIFACT="$ARTIFACT_DIR/run"
RUNTIME_SCRATCH="/tmp/cmq-$SLURM_JOB_ID"
SUITE="$PROJECT/qualification/qwen32b-v1/suite-manifest.json"
TASK="$PROJECT/qualification/qwen32b-v1/tasks/qnm-p01-interval-merge.json"
FREEZE="$PROJECT/qualification/qwen32b-v1/freeze-manifest.json"
TECHNICAL_RERUN_OF=25908
TECHNICAL_RERUN_NUMBER=1
PORT=49784
BASE_URL="http://127.0.0.1:$PORT"
SERVER_PID=

mkdir -p "$ARTIFACT_DIR"

cleanup_server() {
    local cleanup_status=0
    if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
        kill -TERM -- "-$SERVER_PID" 2>/dev/null || cleanup_status=1
        for _ in $(seq 1 30); do
            if ! kill -0 "$SERVER_PID" 2>/dev/null; then
                break
            fi
            sleep 1
        done
        if kill -0 "$SERVER_PID" 2>/dev/null; then
            kill -KILL -- "-$SERVER_PID" 2>/dev/null || cleanup_status=1
        fi
    fi
    if [ -n "$SERVER_PID" ]; then
        wait "$SERVER_PID" 2>/dev/null || true
    fi
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
    cleanup_server || status=1
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
test -f "$TASK"
test -f "$FREEZE"

"$CMPILOT_PY" - "$CPU_GATE" <<'PY'
import json
import sys
from pathlib import Path

record = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if record.get("overall") != "PASS" or not all(record.get("checks", {}).values()):
    raise SystemExit("mandatory CPU qualification gate is not PASS")
PY

git -C "$PROJECT" rev-parse HEAD > "$ARTIFACT_DIR/project-commit.txt"
git -C "$PROJECT" status --porcelain > "$ARTIFACT_DIR/project-status.txt"
test ! -s "$ARTIFACT_DIR/project-status.txt"
git -C "$PROJECT" rev-list -n 1 qwen32b-qualification-v1 > "$ARTIFACT_DIR/freeze-tag-target.txt"
test "$(sed -n '1p' "$ARTIFACT_DIR/freeze-tag-target.txt")" = ba039a0eaddc358d6b7174260c3b3c36169c44c0
sha256sum "$0" "$SUITE" "$TASK" "$FREEZE" > "$ARTIFACT_DIR/runtime-input-hashes.txt"
printf '%s\n' "$TECHNICAL_RERUN_OF" > "$ARTIFACT_DIR/technical-rerun-of.txt"
printf '%s\n' "$TECHNICAL_RERUN_NUMBER" > "$ARTIFACT_DIR/technical-rerun-number.txt"
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
    --task-id qnm-p01-interval-merge \
    --persistent-artifact-root "$ARTIFACT_ROOT" \
    --runtime-path "$RUNTIME_SCRATCH" \
    --record "$ARTIFACT_DIR/runtime-ipc-path-budget.json"
"$CMPILOT_PY" "$PROJECT/scripts/qualification_runtime_path.py" prepare \
    --job-id "$SLURM_JOB_ID" \
    --runtime-path "$RUNTIME_SCRATCH" \
    --record "$ARTIFACT_DIR/runtime-scratch-preparation.json"
export TMPDIR="$RUNTIME_SCRATCH"
export VLLM_RPC_BASE_PATH="$RUNTIME_SCRATCH"

"$VLLM_PY" "$PROJECT/scripts/environment_fingerprint.py" capture \
    --inventory "$ARTIFACT_DIR/environment-inventory.json" \
    --record "$ARTIFACT_DIR/environment-fingerprint.json"
"$VLLM_PY" "$PROJECT/scripts/environment_fingerprint.py" compare \
    --expected "$JOB_25887/environment-fingerprint-v2-final.json" \
    --actual "$ARTIFACT_DIR/environment-fingerprint.json" \
    --classification "$ARTIFACT_DIR/environment-fingerprint-classification.json"
"$VLLM_PY" "$PROJECT/scripts/environment_content_digest.py" \
    --inventory "$ARTIFACT_DIR/environment-content-inventory.json" \
    --record "$ARTIFACT_DIR/environment-content-digest.json" \
    --compare-with-record "$JOB_25887/environment-content-digest-final.json" \
    --classification "$ARTIFACT_DIR/environment-content-classification.json"
"$CMPILOT_PY" - "$ARTIFACT_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
fingerprint = json.loads((root / "environment-fingerprint-classification.json").read_text())
content = json.loads((root / "environment-content-classification.json").read_text())
record = {
    "environment_content": content,
    "environment_fingerprint": fingerprint,
    "pass": bool(fingerprint.get("match") and content.get("authoritative_content_matches")),
    "schema": "qwen32b-qualification-runtime-integrity-v1",
}
(root / "runtime-integrity.json").write_text(
    json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
if not record["pass"]:
    raise SystemExit("frozen runtime integrity mismatch")
PY

"$CMPILOT_PY" - "$PORT" <<'PY'
import socket
import sys

with socket.socket() as probe:
    probe.bind(("127.0.0.1", int(sys.argv[1])))
PY

printf '%q ' "$VLLM_PY" -m vllm.entrypoints.openai.api_server \
    --host 127.0.0.1 --port "$PORT" --model "$MODEL" --tokenizer "$MODEL" \
    --served-model-name "$MODEL" --dtype bfloat16 --tensor-parallel-size 2 \
    --max-model-len 4096 --max-num-seqs 1 --gpu-memory-utilization 0.90 \
    --seed 0 --enforce-eager --guided-decoding-backend lm-format-enforcer \
    > "$ARTIFACT_DIR/server-command.txt"
printf '\n' >> "$ARTIFACT_DIR/server-command.txt"

setsid "$VLLM_PY" -m vllm.entrypoints.openai.api_server \
    --host 127.0.0.1 \
    --port "$PORT" \
    --model "$MODEL" \
    --tokenizer "$MODEL" \
    --served-model-name "$MODEL" \
    --dtype bfloat16 \
    --tensor-parallel-size 2 \
    --max-model-len 4096 \
    --max-num-seqs 1 \
    --gpu-memory-utilization 0.90 \
    --seed 0 \
    --enforce-eager \
    --guided-decoding-backend lm-format-enforcer \
    > "$ARTIFACT_DIR/server.stdout" \
    2> "$ARTIFACT_DIR/server.stderr" &
SERVER_PID=$!
printf '%s\n' "$SERVER_PID" > "$ARTIFACT_DIR/server.pid"

ready=0
for _ in $(seq 1 240); do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        break
    fi
    status=$(/usr/bin/curl --noproxy '*' --silent --output "$ARTIFACT_DIR/health-response.raw" \
        --write-out '%{http_code}' "$BASE_URL/health" || true)
    if [ "$status" = 200 ]; then
        ready=1
        break
    fi
    sleep 1
done
printf '%s\n' "$ready" > "$ARTIFACT_DIR/server-ready.txt"
test "$ready" -eq 1
/usr/bin/curl --noproxy '*' --silent --show-error "$BASE_URL/v1/models" \
    > "$ARTIFACT_DIR/models-response.json"

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
    --agent-timeout 600 \
    --server-pid "$SERVER_PID" \
    --runtime-integrity "$ARTIFACT_DIR/runtime-integrity.json" \
    > "$ARTIFACT_DIR/qualification-runner.stdout" \
    2> "$ARTIFACT_DIR/qualification-runner.stderr"
runner_status=$?
set -e
printf '%s\n' "$runner_status" > "$ARTIFACT_DIR/qualification-runner.exit"
wait "$SERVER_PID" 2>/dev/null || true
SERVER_PID=
test "$runner_status" -eq 0
