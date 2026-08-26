#!/usr/bin/env bash
# Bounded non-confirmatory compatibility smoke. This is not a production run.
#SBATCH --job-name=cmp-devstral-smoke
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=128G
#SBATCH --gpus=2
#SBATCH --constraint=a100
#SBATCH --time=00:45:00
#SBATCH --signal=B:TERM@60
#SBATCH --output=logs/devstral-small-2507/%x-%j.out

set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repository_root"

: "${SLURM_JOB_ID:?This script must run under Slurm}"
: "${DEVSTRAL_ENV_DIR:?Set DEVSTRAL_ENV_DIR to the isolated Devstral environment}"
: "${MINI_SWE_PYTHON:?Set MINI_SWE_PYTHON to the unchanged mini-SWE-agent 2.4.6 interpreter}"
: "${CMPILOT_SHARED_CACHE_ROOT:?Set CMPILOT_SHARED_CACHE_ROOT to the established shared cache root}"
: "${CMPILOT_RUNS_ROOT:?Set CMPILOT_RUNS_ROOT to a non-confirmatory artifact root}"

profile_identity="devstral-small-2507-bd165ab26ceb"
served_model="cmpilot-devstral-small-2507-bd165ab26ceb"
job_root="$CMPILOT_RUNS_ROOT/non-confirmatory-jobs/$profile_identity/slurm-$SLURM_JOB_ID"
server_log_root="$job_root/server"
mkdir -p "$job_root" "$server_log_root"

source "$DEVSTRAL_ENV_DIR/bin/activate"
export CMPILOT_SERVER_LOG_ROOT="$server_log_root"
export VLLM_HOST=127.0.0.1
export VLLM_PORT="${VLLM_PORT:-8000}"
export VLLM_BASE_URL="http://127.0.0.1:$VLLM_PORT/v1"
export CMPILOT_TENSOR_PARALLEL_SIZE=2

python scripts/verify_devstral_environment.py --require-cuda --expected-gpus 2 \
  > "$job_root/environment-attestation.json"
python scripts/attest_model_profile.py --profile devstral-small-2507 --require-cache \
  > "$job_root/model-attestation.json"
"$MINI_SWE_PYTHON" scripts/diagnose_action_protocol.py \
  > "$job_root/action-parser-diagnostic.json"

python - "$job_root/job-manifest.json" <<'PY'
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

manifest = {
    "classification_scope": "non-confirmatory compatibility smoke",
    "submitted_job_id": os.environ["SLURM_JOB_ID"],
    "slurm_job_name": os.environ.get("SLURM_JOB_NAME"),
    "node_count": int(os.environ.get("SLURM_NNODES", "1")),
    "gpu_count": 2,
    "gpu_type": "A100",
    "tensor_parallel_size": 2,
    "wall_time_request": "00:45:00",
    "required_context_length": 131072,
    "actual_maximum_model_length": 131072,
    "model_profile_name": "devstral-small-2507",
    "model_id": "mistralai/Devstral-Small-2507",
    "model_revision": "bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39",
    "tokenizer_revision": "bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39",
    "served_model_name": "cmpilot-devstral-small-2507-bd165ab26ceb",
    "runtime_environment": "cmpilot-devstral-small-2507-v1-cu128",
    "started_at_utc": datetime.now(UTC).isoformat(),
}
Path(sys.argv[1]).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

nvidia-smi \
  --query-gpu=timestamp,index,name,memory.used,memory.total \
  --format=csv,noheader,nounits \
  --loop=5 > "$job_root/gpu-memory.csv" &
memory_monitor_pid=$!
server_pid=""

cleanup() {
  if [[ -n "$server_pid" ]]; then
    kill -TERM -- "-$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
  kill -TERM "$memory_monitor_pid" 2>/dev/null || true
  wait "$memory_monitor_pid" 2>/dev/null || true
}
trap cleanup EXIT TERM INT

setsid scripts/start_devstral_vllm.sh &
server_pid=$!
server_start_epoch=$(date +%s)

healthy=false
for _ in {1..240}; do
  if curl --fail --silent --max-time 2 "http://127.0.0.1:$VLLM_PORT/health" >/dev/null; then
    healthy=true
    break
  fi
  if ! kill -0 "$server_pid" 2>/dev/null; then
    printf '%s\n' 'Devstral server exited before becoming healthy.' >&2
    exit 2
  fi
  sleep 5
done
if [[ "$healthy" != "true" ]]; then
  printf '%s\n' 'Devstral server did not become healthy within 20 minutes.' >&2
  exit 2
fi
server_startup_seconds=$(($(date +%s) - server_start_epoch))
printf 'health=passed\nserver_startup_seconds=%s\n' "$server_startup_seconds" \
  > "$job_root/server-health.txt"

python - "$VLLM_BASE_URL" "$served_model" <<'PY' \
  > "$job_root/served-model-identity.txt"
import sys

from cmpilot.vllm_client import probe_models, validate_model

probe = validate_model(probe_models(sys.argv[1], timeout=10), sys.argv[2])
if not probe.ok or probe.models != (sys.argv[2],):
    raise SystemExit(f"served-model identity check failed: {probe.diagnostic}; models={probe.models}")
print(f"exact served-model identity verified: {probe.models[0]}")
PY

python -m cmpilot smoke \
  --dry-run \
  --profile devstral-small-2507 \
  --base-url "$VLLM_BASE_URL" \
  --mini-python "$MINI_SWE_PYTHON" \
  --runs-root "$job_root/runs" \
  > "$job_root/smoke-dry-run.txt"

set +e
python -m cmpilot smoke \
  --live \
  --profile devstral-small-2507 \
  --base-url "$VLLM_BASE_URL" \
  --mini-python "$MINI_SWE_PYTHON" \
  --runs-root "$job_root/runs" \
  2>&1 | tee "$job_root/smoke-live.txt"
smoke_exit_code=${PIPESTATUS[0]}
set -e

awk -F',' '
  { gpu = $2; gsub(/ /, "", gpu); used = $4 + 0; if (used > peak[gpu]) peak[gpu] = used }
  END { for (gpu in peak) printf "gpu_%s_peak_memory_mib=%d\n", gpu, peak[gpu] }
' "$job_root/gpu-memory.csv" > "$job_root/peak-gpu-memory.txt"
printf '%s\n' "$smoke_exit_code" > "$job_root/smoke-exit-code.txt"

exit "$smoke_exit_code"
