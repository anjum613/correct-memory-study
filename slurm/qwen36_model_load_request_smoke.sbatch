#!/usr/bin/bash
#SBATCH --job-name=qwen36-load-smoke-v1
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=192G
#SBATCH --gres=gpu:a100:2
#SBATCH --time=03:00:00
#SBATCH --no-requeue
#SBATCH --output=/home/s224049759/slurm-logs/qwen36-load-smoke-v1-%j.out
#SBATCH --error=/home/s224049759/slurm-logs/qwen36-load-smoke-v1-%j.err

set -euo pipefail

PROJECT=/home/s224049759/projects/worktrees/qwen32b-protocol-hardening
CMPILOT_PY=/home/s224049759/environments/cmpilot-conda/bin/python
VLLM_PY=/home/s224049759/environments/qwen36-vllm-v1/bin/python
TORCHRUN=/home/s224049759/environments/qwen36-vllm-v1/bin/torchrun
MODEL_ID=Qwen/Qwen3.6-27B
MODEL_REVISION=6a9e13bd6fc8f0983b9b99948120bc37f49c13e9
MODEL=/home/s224049759/model-cache/huggingface/hub/models--Qwen--Qwen3.6-27B/snapshots/6a9e13bd6fc8f0983b9b99948120bc37f49c13e9
MODEL_CACHE=/home/s224049759/model-cache/huggingface
NAMESPACE="$PROJECT/qualification/qwen36-v1"
CANDIDATE_MANIFEST="$NAMESPACE/candidate-freeze-manifest.json"
STAGING_MANIFEST="$NAMESPACE/model-staging-manifest.json"
SUITE_REFERENCE="$NAMESPACE/suite-reference.json"
EXPECTED_ENVIRONMENT="$NAMESPACE/environment-fingerprint.json"
EXPECTED_CONTENT="$NAMESPACE/environment-content-digest.json"
CPU_GATE=/home/s224049759/run-artifacts/qwen36-no-memory-qualification/v1/cpu-preflight-v2/cpu-preflight-result.json
ARTIFACT_ROOT=/home/s224049759/run-artifacts/qwen36-no-memory-qualification/v1/smoke/jobs
ARTIFACT_DIR="$ARTIFACT_ROOT/$SLURM_JOB_ID"
RUNTIME_SCRATCH="/tmp/cmq-$SLURM_JOB_ID"
PORT=49786
BASE_URL="http://127.0.0.1:$PORT/v1"
SERVER_PID=

mkdir -p "$ARTIFACT_DIR"

cleanup_server() {
    local cleanup_status=0
    local observed_exit=not-started
    if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
        kill -TERM -- "-$SERVER_PID" 2>/dev/null || cleanup_status=1
        for _ in $(seq 1 60); do
            if ! kill -0 "$SERVER_PID" 2>/dev/null; then
                observed_exit=terminated
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
    printf '{"cleanup_status":%s,"observed_exit":"%s","pass":%s,"schema":"qwen36-vllm-clean-shutdown-v1"}\n' \
        "$cleanup_status" "$observed_exit" "$([ "$cleanup_status" -eq 0 ] && printf true || printf false)" \
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
    "$CMPILOT_PY" "$PROJECT/scripts/finalize_qwen36_smoke.py" "$ARTIFACT_DIR" || status=1
    trap - EXIT
    exit "$status"
}
trap on_exit EXIT

test -x "$CMPILOT_PY"
test -x "$VLLM_PY"
test -x "$TORCHRUN"
test -d "$MODEL"
test -f "$CANDIDATE_MANIFEST"
test -f "$STAGING_MANIFEST"
test -f "$SUITE_REFERENCE"
test -f "$EXPECTED_ENVIRONMENT"
test -f "$EXPECTED_CONTENT"
test -f "$CPU_GATE"

"$CMPILOT_PY" - "$CPU_GATE" "$CANDIDATE_MANIFEST" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

gate_path, candidate_path = map(Path, sys.argv[1:])
gate = json.loads(gate_path.read_text(encoding="utf-8"))
candidate_sha = hashlib.sha256(candidate_path.read_bytes()).hexdigest()
if gate.get("overall") != "PASS" or not all(gate.get("checks", {}).values()):
    raise SystemExit("mandatory Qwen3.6 CPU gate is not an all-check PASS")
if gate.get("candidate_freeze_manifest_sha256") != candidate_sha:
    raise SystemExit("candidate freeze manifest changed after CPU validation")
PY

git -C "$PROJECT" rev-parse HEAD > "$ARTIFACT_DIR/project-commit.txt"
git -C "$PROJECT" status --porcelain > "$ARTIFACT_DIR/project-status.txt"
test ! -s "$ARTIFACT_DIR/project-status.txt"
git -C "$PROJECT" rev-list -n 1 qwen32b-qualification-v1 \
    > "$ARTIFACT_DIR/qwen32b-freeze-tag-target.txt"
test "$(sed -n '1p' "$ARTIFACT_DIR/qwen32b-freeze-tag-target.txt")" \
    = ba039a0eaddc358d6b7174260c3b3c36169c44c0
sha256sum "$0" "$CANDIDATE_MANIFEST" "$STAGING_MANIFEST" "$SUITE_REFERENCE" \
    "$EXPECTED_ENVIRONMENT" "$EXPECTED_CONTENT" "$CPU_GATE" \
    > "$ARTIFACT_DIR/runtime-input-hashes.txt"
printf '%s\n' "$MODEL_ID" > "$ARTIFACT_DIR/model-id.txt"
printf '%s\n' "$MODEL_REVISION" > "$ARTIFACT_DIR/model-revision.txt"
date -u +%Y-%m-%dT%H:%M:%SZ > "$ARTIFACT_DIR/job-started-utc.txt"
hostname > "$ARTIFACT_DIR/hostname.txt"
env | awk -F= '$1 ~ /^SLURM_/ {print}' | LC_ALL=C sort \
    > "$ARTIFACT_DIR/slurm-environment.txt"

export HF_HOME="$MODEL_CACHE"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_HUB_DISABLE_TELEMETRY=1
export TOKENIZERS_PARALLELISM=false
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export NO_PROXY=127.0.0.1,localhost
export no_proxy=127.0.0.1,localhost
export TMPDIR="$RUNTIME_SCRATCH"
export TEMP="$RUNTIME_SCRATCH"
export TMP="$RUNTIME_SCRATCH"
export VLLM_RPC_BASE_PATH="$RUNTIME_SCRATCH"
export NCCL_DEBUG=INFO

"$CMPILOT_PY" "$PROJECT/scripts/qualification_runtime_path.py" validate \
    --job-id "$SLURM_JOB_ID" \
    --task-id qwen36-model-load-request-smoke-v1 \
    --persistent-artifact-root "$ARTIFACT_ROOT" \
    --runtime-path "$RUNTIME_SCRATCH" \
    --record "$ARTIFACT_DIR/runtime-ipc-path-budget.json"
"$CMPILOT_PY" "$PROJECT/scripts/qualification_runtime_path.py" prepare \
    --job-id "$SLURM_JOB_ID" \
    --runtime-path "$RUNTIME_SCRATCH" \
    --record "$ARTIFACT_DIR/runtime-scratch-preparation.json"
printf 'TMPDIR=%s\nTEMP=%s\nTMP=%s\nVLLM_RPC_BASE_PATH=%s\n' \
    "$TMPDIR" "$TEMP" "$TMP" "$VLLM_RPC_BASE_PATH" \
    > "$ARTIFACT_DIR/runtime-environment.txt"

"$VLLM_PY" "$PROJECT/scripts/verify_qwen36_environment.py" \
    --output-directory "$ARTIFACT_DIR/environment-verification" \
    --expected-fingerprint "$EXPECTED_ENVIRONMENT" \
    --expected-content "$EXPECTED_CONTENT" \
    > "$ARTIFACT_DIR/environment-verification.stdout" \
    2> "$ARTIFACT_DIR/environment-verification.stderr"

/usr/bin/nvidia-smi > "$ARTIFACT_DIR/nvidia-smi-initial.txt"
/usr/bin/nvidia-smi -L > "$ARTIFACT_DIR/nvidia-smi-list.txt"
/usr/bin/nvidia-smi topo -m > "$ARTIFACT_DIR/nvidia-smi-topology.txt"
/usr/bin/nvidia-smi -q -d MIG > "$ARTIFACT_DIR/nvidia-smi-mig.txt"
/usr/bin/nvidia-smi --query-gpu=index,name,uuid,memory.total \
    --format=csv,noheader,nounits > "$ARTIFACT_DIR/gpu-allocation.csv"
"$TORCHRUN" --standalone --nnodes=1 --nproc-per-node=2 \
    "$PROJECT/scripts/qwen36_gpu_probe.py" \
    --artifact-directory "$ARTIFACT_DIR" \
    > "$ARTIFACT_DIR/nccl-probe.stdout" \
    2> "$ARTIFACT_DIR/nccl-probe.stderr"
"$CMPILOT_PY" - "$ARTIFACT_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
records = [json.loads((root / f"nccl-rank-{rank}.json").read_text()) for rank in (0, 1)]
if not all(record.get("pass") is True for record in records):
    raise SystemExit("two-rank NCCL/CUDA probe failed")
PY

"$CMPILOT_PY" - "$PORT" <<'PY'
import socket
import sys

with socket.socket() as probe:
    probe.bind(("127.0.0.1", int(sys.argv[1])))
PY

printf '%q ' "$VLLM_PY" -m vllm.entrypoints.openai.api_server \
    --host 127.0.0.1 --port "$PORT" --model "$MODEL" --tokenizer "$MODEL" \
    --served-model-name "$MODEL_ID" --dtype bfloat16 --tensor-parallel-size 2 \
    --max-model-len 32768 --max-num-seqs 1 --gpu-memory-utilization 0.90 \
    --seed 0 --enforce-eager --reasoning-parser qwen3 --language-model-only \
    --generation-config vllm > "$ARTIFACT_DIR/server-command.txt"
printf '\n' >> "$ARTIFACT_DIR/server-command.txt"

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
    --seed 0 \
    --enforce-eager \
    --reasoning-parser qwen3 \
    --language-model-only \
    --generation-config vllm \
    > "$ARTIFACT_DIR/server.stdout" \
    2> "$ARTIFACT_DIR/server.stderr" &
SERVER_PID=$!
printf '%s\n' "$SERVER_PID" > "$ARTIFACT_DIR/server.pid"

"$CMPILOT_PY" "$PROJECT/scripts/qwen36_smoke_client.py" \
    --artifact-directory "$ARTIFACT_DIR" \
    --base-url "$BASE_URL" \
    --server-pid "$SERVER_PID" \
    --startup-timeout 1800 \
    > "$ARTIFACT_DIR/smoke-client.stdout" \
    2> "$ARTIFACT_DIR/smoke-client.stderr"

cleanup_server
sleep 5
/usr/bin/nvidia-smi --query-gpu=index,name,memory.total,memory.used,memory.free \
    --format=csv,noheader,nounits > "$ARTIFACT_DIR/gpu-memory-after-shutdown.csv"
