#!/usr/bin/env bash
# Dedicated, offline-by-default Devstral launcher. The Qwen launcher is separate.
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
profile_name="devstral-small-2507"
profile_identity="devstral-small-2507-bd165ab26ceb"
model_revision="bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39"
model_cache_key="models--mistralai--Devstral-Small-2507"

: "${CMPILOT_SHARED_CACHE_ROOT:?Set CMPILOT_SHARED_CACHE_ROOT to the established shared cache root}"
: "${CMPILOT_SERVER_LOG_ROOT:?Set CMPILOT_SERVER_LOG_ROOT to a model-specific writable log root}"
VLLM_HOST="${VLLM_HOST:-127.0.0.1}"
VLLM_PORT="${VLLM_PORT:-8000}"
CMPILOT_TENSOR_PARALLEL_SIZE="${CMPILOT_TENSOR_PARALLEL_SIZE:-2}"

if [[ "$CMPILOT_TENSOR_PARALLEL_SIZE" != "2" && "$CMPILOT_TENSOR_PARALLEL_SIZE" != "4" ]]; then
  printf 'Devstral tensor parallel size must be 2, or 4 after demonstrated memory pressure.\n' >&2
  exit 2
fi
if [[ "$CMPILOT_TENSOR_PARALLEL_SIZE" == "4" ]]; then
  : "${CMPILOT_TP4_FALLBACK_EVIDENCE:?Set CMPILOT_TP4_FALLBACK_EVIDENCE to the failed two-GPU memory log}"
  if [[ ! -f "$CMPILOT_TP4_FALLBACK_EVIDENCE" ]]; then
    printf 'Four-GPU fallback evidence does not exist: %s\n' "$CMPILOT_TP4_FALLBACK_EVIDENCE" >&2
    exit 2
  fi
fi
if ! [[ "$VLLM_PORT" =~ ^[1-9][0-9]{0,4}$ ]] || (( VLLM_PORT > 65535 )); then
  printf 'VLLM_PORT must be a valid TCP port: %s\n' "$VLLM_PORT" >&2
  exit 2
fi
if ! command -v vllm >/dev/null 2>&1; then
  printf 'vLLM is unavailable; activate the isolated Devstral environment.\n' >&2
  exit 2
fi

export HF_HOME="$CMPILOT_SHARED_CACHE_ROOT/huggingface"
snapshot="$HF_HOME/hub/$model_cache_key/snapshots/$model_revision"
for required_file in config.json tekken.json model.safetensors.index.json; do
  if [[ ! -f "$snapshot/$required_file" ]]; then
    printf 'Exact offline Devstral snapshot is incomplete; missing %s\n' "$snapshot/$required_file" >&2
    exit 2
  fi
done

cache_root="$CMPILOT_SHARED_CACHE_ROOT/runtime/$profile_identity"
export VLLM_CACHE_ROOT="$cache_root/vllm"
export TRITON_CACHE_DIR="$cache_root/triton"
export TORCHINDUCTOR_CACHE_DIR="$cache_root/torchinductor"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
mkdir -p "$VLLM_CACHE_ROOT" "$TRITON_CACHE_DIR" "$TORCHINDUCTOR_CACHE_DIR" "$CMPILOT_SERVER_LOG_ROOT"

mapfile -t model_arguments < <(
  PYTHONPATH="$repository_root/src${PYTHONPATH:+:$PYTHONPATH}" \
    python -m cmpilot model-profile-arguments --profile "$profile_name"
)
if [[ "$CMPILOT_TENSOR_PARALLEL_SIZE" == "4" ]]; then
  for ((index = 0; index < ${#model_arguments[@]}; index++)); do
    if [[ "${model_arguments[$index]}" == "--tensor-parallel-size" ]]; then
      model_arguments[$((index + 1))]="4"
      break
    fi
  done
fi

log_file="$CMPILOT_SERVER_LOG_ROOT/vllm-$profile_identity-tp$CMPILOT_TENSOR_PARALLEL_SIZE-${SLURM_JOB_ID:-manual}.log"
printf 'Starting profile %s at revision %s with TP=%s; log: %s\n' \
  "$profile_name" "$model_revision" "$CMPILOT_TENSOR_PARALLEL_SIZE" "$log_file"
printf '%s\n' 'Hugging Face and Transformers are offline; no model download will be attempted.'

vllm serve "${model_arguments[@]}" \
  --host "$VLLM_HOST" \
  --port "$VLLM_PORT" 2>&1 | tee "$log_file"
