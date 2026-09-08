#!/usr/bin/env bash
# Start the local vLLM server needed by the engineering calculator smoke test.
set -euo pipefail

show_help() {
  printf '%s\n' \
    'Usage: scripts/start_vllm_smoke.sh' \
    '' \
    'Required environment variables:' \
    '  VLLM_SINGULARITY_IMAGE  Path to the vLLM Singularity image.' \
    '  VLLM_LOG_DIR            Directory where foreground server logs are written.' \
    '' \
    'Optional environment variables:' \
    '  VLLM_MODEL              Model ID (default: Qwen/Qwen2.5-Coder-1.5B-Instruct).' \
    '  VLLM_HOST               Listen host (default: 127.0.0.1).' \
    '  VLLM_PORT               Listen port (default: 8000).' \
    '  VLLM_DTYPE              vLLM dtype (default: half).' \
    '                            Turing-generation Quadro RTX 5000 GPUs do not support bfloat16.' \
    '' \
    'The process remains in the foreground. Press Ctrl-C to stop it cleanly.'
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  show_help
  exit 0
fi
if [[ $# -ne 0 ]]; then
  show_help >&2
  exit 2
fi

: "${VLLM_SINGULARITY_IMAGE:?Set VLLM_SINGULARITY_IMAGE to the vLLM .sif file}"
: "${VLLM_LOG_DIR:?Set VLLM_LOG_DIR to a user-owned log directory}"
VLLM_MODEL="${VLLM_MODEL:-Qwen/Qwen2.5-Coder-1.5B-Instruct}"
VLLM_HOST="${VLLM_HOST:-127.0.0.1}"
VLLM_PORT="${VLLM_PORT:-8000}"
VLLM_DTYPE="${VLLM_DTYPE:-half}"

if [[ ! "$VLLM_PORT" =~ ^[1-9][0-9]{0,4}$ ]] || (( VLLM_PORT > 65535 )); then
  printf 'VLLM_PORT must be a valid TCP port: %s\n' "$VLLM_PORT" >&2
  exit 2
fi
if [[ ! -f "$VLLM_SINGULARITY_IMAGE" ]]; then
  printf 'vLLM Singularity image does not exist: %s\n' "$VLLM_SINGULARITY_IMAGE" >&2
  exit 2
fi
if ! command -v singularity >/dev/null 2>&1; then
  printf 'Singularity is not available on PATH.\n' >&2
  exit 2
fi
if ! command -v ss >/dev/null 2>&1; then
  printf 'The ss command is required to check port %s.\n' "$VLLM_PORT" >&2
  exit 2
fi

endpoint="http://127.0.0.1:${VLLM_PORT}/v1/models"
port_is_listening() {
  ss -ltnH | awk -v port="$VLLM_PORT" '$4 ~ (":" port "$") { found = 1 } END { exit !found }'
}

server_has_expected_model() {
  python3 - "$endpoint" "$VLLM_MODEL" <<'PY'
import json
import sys
from urllib.request import urlopen

endpoint, expected_model = sys.argv[1:]
try:
    with urlopen(endpoint, timeout=2) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP {response.status}")
        payload = json.loads(response.read().decode("utf-8"))
        models = {item["id"] for item in payload["data"] if isinstance(item, dict) and isinstance(item.get("id"), str)}
except Exception as error:
    print(f"port is occupied but {endpoint} is unhealthy: {error}", file=sys.stderr)
    raise SystemExit(1)
if expected_model not in models:
    print(
        f"port is occupied by a healthy service, but it does not serve {expected_model}; "
        f"reported models: {', '.join(sorted(models)) or '(none)'}",
        file=sys.stderr,
    )
    raise SystemExit(1)
print(f"A healthy vLLM server for {expected_model} is already listening on port {endpoint.rsplit(':', 1)[1].split('/', 1)[0]}.")
PY
}

if port_is_listening; then
  if server_has_expected_model; then
    exit 0
  fi
  printf 'Refusing to replace the process already listening on port %s.\n' "$VLLM_PORT" >&2
  exit 1
fi

mkdir -p "$VLLM_LOG_DIR"
log_file="$VLLM_LOG_DIR/vllm-smoke-$(date -u +%Y%m%d-%H%M%S).log"
printf 'Starting vLLM for %s on %s:%s; logs: %s\n' "$VLLM_MODEL" "$VLLM_HOST" "$VLLM_PORT" "$log_file"
printf 'Selected vLLM dtype: %s\n' "$VLLM_DTYPE"
printf '%s\n' 'Selected guided-decoding backend: lm-format-enforcer'
printf '%s\n' 'Native tool calling is enabled because mini-SWE-agent DefaultAgent uses a native Bash tool.'
printf '%s\n' 'Model downloads are disabled; the requested model must already be available in the workstation cache.'

HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
SINGULARITYENV_HF_HUB_OFFLINE=1 SINGULARITYENV_TRANSFORMERS_OFFLINE=1 \
singularity exec --nv "$VLLM_SINGULARITY_IMAGE" \
  vllm serve "$VLLM_MODEL" \
  --host "$VLLM_HOST" \
  --port "$VLLM_PORT" \
  --dtype "$VLLM_DTYPE" \
  --guided-decoding-backend lm-format-enforcer \
  --enable-auto-tool-choice \
  --tool-call-parser hermes 2>&1 | tee "$log_file"
