#!/usr/bin/env bash
# Start the pinned Qwen3-Coder FP8 vLLM service inside a RunPod vLLM Pod.
set -euo pipefail

model="Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8"
revision="e8ab3f2db9e388999a004eea5a31c16a8b517bc0"
served_name="qwen3-coder-30b-a3b-instruct-fp8"
host="${VLLM_HOST:-127.0.0.1}"
port="${VLLM_PORT:-8000}"
workspace="${RUNPOD_WORKSPACE:-/workspace}"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  printf '%s\n' \
    'Usage: scripts/start_qwen3_coder_fp8_runpod.sh' \
    '' \
    'Run inside a RunPod vLLM Pod with 2x L40S and /workspace persistent storage.' \
    'The server binds to 127.0.0.1:8000 by default for SSH port forwarding.' \
    '' \
    'Optional: VLLM_HOST, VLLM_PORT, RUNPOD_WORKSPACE, HF_TOKEN.'
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

export HF_HOME="$workspace/huggingface"
export HUGGINGFACE_HUB_CACHE="$HF_HOME/hub"
export VLLM_CACHE_ROOT="$workspace/vllm-cache"
mkdir -p "$HUGGINGFACE_HUB_CACHE" "$VLLM_CACHE_ROOT" "$workspace/logs"

version_file="$workspace/logs/qwen3-vllm-runtime.txt"
{
  printf 'started_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'model=%s\nrevision=%s\nserved_model_name=%s\n' "$model" "$revision" "$served_name"
  printf 'vllm_version='; vllm --version
  nvidia-smi --query-gpu=index,name,memory.total,driver_version --format=csv,noheader
} | tee "$version_file"

printf 'Starting pinned Qwen3-Coder FP8 on %s:%s; weights/cache persist under %s.\n' \
  "$host" "$port" "$workspace"
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
  --download-dir "$HUGGINGFACE_HUB_CACHE"
