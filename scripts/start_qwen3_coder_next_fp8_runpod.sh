#!/usr/bin/env bash
# Start the pinned Qwen3-Coder-Next FP8 vLLM service on the existing RunPod.
set -euo pipefail

model="Qwen/Qwen3-Coder-Next-FP8"
revision="da6e2ed27304dd39abadd9c82ef50e8de67bdd4c"
served_name="qwen3-coder-next-fp8"
host="${VLLM_HOST:-127.0.0.1}"
port="${VLLM_PORT:-8000}"
workspace="${RUNPOD_WORKSPACE:-/workspace}"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  printf '%s\n' \
    'Usage: scripts/start_qwen3_coder_next_fp8_runpod.sh' \
    '' \
    'Run inside the existing RunPod vLLM Pod with 2x L40S.' \
    'The server binds to 127.0.0.1:8000 for SSH forwarding.' \
    'The pinned weights/cache persist under /workspace/qwen3-coder-next-hf.'
  exit 0
fi
if [[ $# -ne 0 ]]; then
  printf 'This script accepts no positional arguments. Use --help.\n' >&2
  exit 2
fi
if [[ ! "$port" =~ ^[1-9][0-9]{0,4}$ ]] || (( port > 65535 )); then
  printf 'VLLM_PORT must be a valid TCP port: %s\n' "$port" >&2
  exit 2
fi
if [[ ! -d "$workspace" ]]; then
  printf 'Persistent workspace is missing: %s\n' "$workspace" >&2
  exit 2
fi
if ! command -v nvidia-smi >/dev/null 2>&1 || ! command -v vllm >/dev/null 2>&1; then
  printf 'The pod must provide both nvidia-smi and vllm.\n' >&2
  exit 2
fi
gpu_count="$(nvidia-smi --query-gpu=name --format=csv,noheader | wc -l)"
if (( gpu_count < 2 )); then
  printf 'Two GPUs are required for tensor parallelism; found %s.\n' "$gpu_count" >&2
  exit 2
fi

export HF_HOME="$workspace/qwen3-coder-next-hf"
export HUGGINGFACE_HUB_CACHE="$HF_HOME/hub"
export VLLM_CACHE_ROOT="$workspace/vllm-cache-qwen3-coder-next"
export NCCL_P2P_DISABLE="${NCCL_P2P_DISABLE:-1}"
export NCCL_IB_DISABLE="${NCCL_IB_DISABLE:-1}"
mkdir -p "$HUGGINGFACE_HUB_CACHE" "$VLLM_CACHE_ROOT" "$workspace/logs"

version_file="$workspace/logs/qwen3-coder-next-vllm-runtime.txt"
{
  printf 'started_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'model=%s\nrevision=%s\nserved_model_name=%s\n' "$model" "$revision" "$served_name"
  printf 'vllm_version='; vllm --version
  nvidia-smi --query-gpu=index,name,memory.total,driver_version --format=csv,noheader
} | tee "$version_file"

printf 'Starting pinned Qwen3-Coder-Next FP8 on %s:%s.\n' "$host" "$port"
exec vllm serve "$model" \
  --revision "$revision" \
  --served-model-name "$served_name" \
  --host "$host" \
  --port "$port" \
  --tensor-parallel-size 2 \
  --max-model-len 4096 \
  --max-num-seqs 2 \
  --gpu-memory-utilization 0.90 \
  --generation-config vllm \
  --disable-custom-all-reduce \
  --download-dir "$HUGGINGFACE_HUB_CACHE"
