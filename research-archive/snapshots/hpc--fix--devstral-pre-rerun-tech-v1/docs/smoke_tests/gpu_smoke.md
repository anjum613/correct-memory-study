# GPU smoke test 0

This is the first hardware-only GPU smoke test. It does not download model
weights and does not invoke vLLM, Transformers, or mini-SWE-agent.

## Submit

```bash
sbatch slurm/gpu_smoke.sbatch
```

The initial RTX 6000 allocation was unhealthy, so this run uses the first available fallback: one RTX A4000 Ada GPU, four CPUs, 16 GiB RAM, and five minutes.
It loads the cluster module `pytorch/2.7.1_py3.13` and runs
`scripts/gpu_smoke.py`.

## Checks

For every GPU visible through the Slurm allocation, the program reports the
Python, PyTorch, CUDA, and cuDNN versions; GPU name, VRAM, and compute
capability; then runs finite FP32 and FP16 matrix multiplications and BF16
when PyTorch reports it is supported. CUDA is synchronized around each timed
operation and allocated/reserved memory is recorded.

The program exits nonzero when CUDA or a GPU is unavailable, FP32 fails, or a
result is NaN/infinite. A machine-readable `gpu_smoke_result.json` is written
using the project's redacting artifact helper.

## Artifacts

For job `<job-id>`, immutable run material is placed under:

```text
/home/s224049759/run-artifacts/smoke-0/<job-id>/
```

This includes `stdout.txt`, `stderr.txt`, `gpu_smoke_result.json`, hostname,
Slurm environment, module list, `nvidia-smi`, topology, exact Git commit,
Git status, and timestamps. Slurm's stdout and stderr are additionally kept
in `/home/s224049759/slurm-logs/gpu-smoke-<job-id>.out` and `.err`.
