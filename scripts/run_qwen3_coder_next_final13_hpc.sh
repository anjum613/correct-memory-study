#!/usr/bin/env bash
# Run on one Deakin CPU allocation: tunnel, canary, then 104 Coder-Next cells.
set -euo pipefail

: "${RUNPOD_SSH_HOST:?Set RUNPOD_SSH_HOST to the public pod IP or hostname}"
: "${RUNPOD_SSH_PORT:?Set RUNPOD_SSH_PORT to the mapped SSH port}"
: "${CMPILOT_RUNS_ROOT:?Set CMPILOT_RUNS_ROOT to a new persistent result directory}"

runpod_user="${RUNPOD_SSH_USER:-root}"
runpod_ssh_key="${RUNPOD_SSH_KEY:-/home/s224049759/.ssh/id_ed25519_runpod_qwen3}"
runpod_known_hosts="${RUNPOD_KNOWN_HOSTS:-/home/s224049759/.ssh/known_hosts_runpod_qwen3_direct}"
remote_vllm_port="${RUNPOD_VLLM_PORT:-8000}"
local_vllm_port="${LOCAL_VLLM_PORT:-18000}"
workers="${CMPILOT_WORKERS:-2}"
mini_python="${MINI_SWE_PYTHON:-/home/s224049759/environments/mini-swe-agent-smoke/bin/python}"
tokenizer_path="${QWEN3_CODER_NEXT_TOKENIZER_PATH:-/home/s224049759/model-cache/qwen3-coder-next-fp8/da6e2ed27304dd39abadd9c82ef50e8de67bdd4c}"
v3_dependency_path="${QWEN3_CODER_NEXT_V3_DEPENDENCY_PATH:-/home/s224049759/environments/qwen36-vllm-v1/lib/python3.12/site-packages}"
base_url="http://127.0.0.1:${local_vllm_port}/v1"

if [[ ! -f "$runpod_ssh_key" ]]; then
  printf 'RunPod SSH private key not found: %s\n' "$runpod_ssh_key" >&2
  exit 2
fi
if [[ ! "$RUNPOD_SSH_PORT" =~ ^[1-9][0-9]{0,4}$ ]] || (( RUNPOD_SSH_PORT > 65535 )); then
  printf 'RUNPOD_SSH_PORT is invalid: %s\n' "$RUNPOD_SSH_PORT" >&2
  exit 2
fi

mkdir -p "$CMPILOT_RUNS_ROOT"
tunnel_log="$CMPILOT_RUNS_ROOT/ssh-tunnel.log"
ssh \
  -N \
  -i "$runpod_ssh_key" \
  -p "$RUNPOD_SSH_PORT" \
  -L "127.0.0.1:${local_vllm_port}:127.0.0.1:${remote_vllm_port}" \
  -o BatchMode=yes \
  -o ExitOnForwardFailure=yes \
  -o IdentitiesOnly=yes \
  -o ServerAliveInterval=15 \
  -o ServerAliveCountMax=4 \
  -o StrictHostKeyChecking=yes \
  -o "UserKnownHostsFile=${runpod_known_hosts}" \
  "${runpod_user}@${RUNPOD_SSH_HOST}" >"$tunnel_log" 2>&1 &
tunnel_pid=$!
cleanup() {
  kill "$tunnel_pid" 2>/dev/null || true
  wait "$tunnel_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

ready=0
for _ in $(seq 1 30); do
  if ! kill -0 "$tunnel_pid" 2>/dev/null; then
    printf 'SSH tunnel exited before vLLM became reachable; see %s\n' "$tunnel_log" >&2
    exit 2
  fi
  if "$mini_python" - "$base_url/models" <<'PY' >/dev/null 2>&1
import sys
from urllib.request import urlopen
with urlopen(sys.argv[1], timeout=2) as response:
    raise SystemExit(0 if response.status == 200 else 1)
PY
  then
    ready=1
    break
  fi
  sleep 2
done
if (( ready == 0 )); then
  printf 'vLLM did not become reachable through the SSH tunnel.\n' >&2
  exit 2
fi

common=(
  --recommended
  --base-url "$base_url"
  --mini-python "$mini_python"
  --tokenizer-path "$tokenizer_path"
  --v3-dependency-path "$v3_dependency_path"
  --run-root "$CMPILOT_RUNS_ROOT"
)
"$mini_python" scripts/run_qwen3_coder_next_final13.py preflight "${common[@]}"
if [[ "${CMPILOT_SKIP_CANARY:-0}" != "1" ]]; then
  "$mini_python" scripts/run_qwen3_coder_next_final13.py canary "${common[@]}"
fi
if [[ -n "${CMPILOT_PILOT_INDEX:-}" ]]; then
  if [[ ! "$CMPILOT_PILOT_INDEX" =~ ^[0-9]+$ ]]; then
    printf 'CMPILOT_PILOT_INDEX must be a nonnegative integer.\n' >&2
    exit 2
  fi
  "$mini_python" scripts/run_qwen3_coder_next_final13.py cell \
    "${common[@]}" --index "$CMPILOT_PILOT_INDEX"
  exit 0
fi
"$mini_python" scripts/run_qwen3_coder_next_final13.py batch "${common[@]}" --workers "$workers"
