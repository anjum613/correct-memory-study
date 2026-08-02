# Model inference smoke test 1

This smoke test validates one deterministic, single-GPU Hugging Face Transformers
inference request on a single allocated RTX 4000 SFF Ada GPU. It intentionally
excludes vLLM, containers, quantization, multi-GPU execution, mini-SWE-agent,
and model serving.

## Environment

The Slurm job loads the cluster module pytorch/2.7.1_py3.13 and runs the
separate system-site-packages virtual environment at
/home/s224049759/environments/model-smoke-transformers. The environment adds
only Transformers and its required inference dependencies; it does not modify
the cmpilot-conda test environment.

The job sets:

- HF_HOME=/home/s224049759/model-cache/huggingface
- HF_HUB_DISABLE_TELEMETRY=1
- TOKENIZERS_PARALLELISM=false

## Run

Run the syntax check before submission:

    bash -n slurm/model_inference_smoke.sbatch
    module purge
    module load pytorch/2.7.1_py3.13
    PYTHONPATH=src /home/s224049759/environments/model-smoke-transformers/bin/python -m py_compile scripts/model_inference_smoke.py
    module purge

Submit exactly one job:

    sbatch slurm/model_inference_smoke.sbatch

The job requests one rtxa4000ada GPU, four CPUs, 24 GiB of RAM, and 20
minutes. It loads Qwen/Qwen2.5-Coder-1.5B-Instruct in BF16, applies its chat
template to the fixed safe_divide prompt, warms up once, and records a
deterministic generation with do_sample=False, max_new_tokens=128, and
use_cache=True.

## Artifacts

Every Slurm job writes a distinct directory:

    /home/s224049759/run-artifacts/model-smoke-1/<job-id>/

It contains captured stdout and stderr, redacted Slurm/CUDA/Hugging Face
environment settings, hostname, module list, NVIDIA-SMI reports, Git commit and
status, timestamps, pip freeze, exact model revision, generated text, an
append-only JSONL event log, and the immutable JSON result.

Scheduler stdout and stderr are stored under:

    /home/s224049759/slurm-logs/model-inference-smoke-<job-id>.out
    /home/s224049759/slurm-logs/model-inference-smoke-<job-id>.err
