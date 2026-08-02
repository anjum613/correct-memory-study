# vLLM server smoke test 2

This smoke test launches a single-GPU, loopback-only OpenAI-compatible vLLM
server, verifies its model listing, sends one deterministic chat-completions
request, validates the coding response, and terminates the server.

## Environment

The isolated environment is
/home/s224049759/environments/vllm-smoke. It is created with uv and Python
3.12 without system-site-packages and without the cluster PyTorch module.

The pinned vLLM release is 0.6.1.post2. It uses CUDA 12.1 binaries, compatible
with the cluster's 535.288.01 driver. The job activates only this environment
after module purge and sets:

- HF_HOME=/home/s224049759/model-cache/huggingface
- HF_HUB_DISABLE_TELEMETRY=1
- TOKENIZERS_PARALLELISM=false

The job reuses the cached Qwen/Qwen2.5-Coder-1.5B-Instruct revision
2e1fd397ee46e1388853d2af2c993145b0f1098a.

## Compatibility note

vLLM 0.6.1.post2 does not expose the newer --generation-config CLI option.
The server therefore uses its compatible defaults, while the smoke request
explicitly sets temperature to zero. All requested host, port, revision, BF16,
model-length, and GPU-memory-utilization settings are used exactly.

## Run

    bash -n slurm/vllm_server_smoke.sbatch
    /home/s224049759/environments/vllm-smoke/bin/python -m py_compile scripts/vllm_server_smoke_client.py
    sbatch slurm/vllm_server_smoke.sbatch

The job requests one rtxa4000ada GPU, four CPUs, 32 GiB RAM, and 20 minutes.
It binds only to 127.0.0.1:8000, waits up to 180 seconds for health, checks
/v1/models, sends one /v1/chat/completions request, and validates safe_divide,
ValueError, and a zero-divisor check.

The health probe accepts every HTTP 2xx response, including vLLM's plain-text
response. It records the status, response headers, and body without attempting
JSON decoding, then captures the during-serving NVIDIA-SMI snapshot before
requesting /v1/models.

## Harness history

- Job 24570 failed before server launch because its logging harness invoked the
  vLLM CLI with an invalid version command. It was not a GPU, model, or vLLM
  serving failure.
- Job 24578 started and loaded the server successfully, but its client harness
  incorrectly attempted to JSON-decode vLLM's plain-text HTTP 200 health
  response. It was not a GPU, model, or vLLM serving failure.


## Artifacts

Each job writes an immutable directory:

    /home/s224049759/run-artifacts/vllm-smoke-2/<job-id>/

It includes server and client logs, result and response JSON, model revision,
timestamps, process-cleanup evidence, NVIDIA-SMI before/during/after snapshots,
module and environment records, pip freeze, and Git provenance. Scheduler logs
are stored in /home/s224049759/slurm-logs/vllm-server-smoke-<job-id>.out and
/home/s224049759/slurm-logs/vllm-server-smoke-<job-id>.err.
