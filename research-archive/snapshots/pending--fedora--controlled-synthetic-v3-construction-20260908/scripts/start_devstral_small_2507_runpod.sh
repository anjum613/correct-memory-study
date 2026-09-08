#!/usr/bin/env bash
# Start pinned Devstral Small 2507 in its official Mistral vLLM format.
set -euo pipefail

model="mistralai/Devstral-Small-2507"
revision="bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39"
served_name="devstral-small-2507"
host="${VLLM_HOST:-127.0.0.1}"
port="${VLLM_PORT:-8000}"
workspace="${RUNPOD_WORKSPACE:-/workspace}"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  printf '%s\n' 'Usage: scripts/start_devstral_small_2507_runpod.sh' \
    '' 'Run inside the existing 2x L40S RunPod vLLM Pod.'
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
gpu_count="$(nvidia-smi --query-gpu=name --format=csv,noheader | wc -l)"
if (( gpu_count < 2 )); then
  printf 'Two GPUs are required; found %s.\n' "$gpu_count" >&2
  exit 2
fi

export HF_HOME="$workspace/devstral-hf"
export HUGGINGFACE_HUB_CACHE="$HF_HOME/hub"
export VLLM_CACHE_ROOT="$workspace/vllm-cache-devstral"
export NCCL_P2P_DISABLE="${NCCL_P2P_DISABLE:-1}"
export NCCL_IB_DISABLE="${NCCL_IB_DISABLE:-1}"
mkdir -p "$HUGGINGFACE_HUB_CACHE" "$VLLM_CACHE_ROOT" "$workspace/logs"

version_file="$workspace/logs/devstral-small-2507-vllm-runtime.txt"
{
  printf 'started_at_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'model=%s\nrevision=%s\nserved_model_name=%s\n' "$model" "$revision" "$served_name"
  printf 'vllm_version='; vllm --version
  nvidia-smi --query-gpu=index,name,memory.total,driver_version --format=csv,noheader
} | tee "$version_file"

exec vllm serve "$model" \
  --revision "$revision" \
  --served-model-name "$served_name" \
  --host "$host" \
  --port "$port" \
  --dtype bfloat16 \
  --tensor-parallel-size 2 \
  --max-model-len 32768 \
  --max-num-seqs 2 \
  --gpu-memory-utilization 0.90 \
  --generation-config vllm \
  --tokenizer-mode mistral \
  --config-format mistral \
  --load-format mistral \
  --enable-auto-tool-choice \
  --tool-call-parser mistral \
  --disable-custom-all-reduce \
  --download-dir "$HUGGINGFACE_HUB_CACHE"
