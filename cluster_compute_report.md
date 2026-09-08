# Deakin HPC compute and account report

Collected on **2026-08-02 17:18 AEST** from the Deakin HPC login node. Raw command output is retained alongside this report. Evidence labels are deliberate:

- **[Slurm]**: directly reported by Slurm at collection time.
- **[Measured]**: observed in an allocated compute job. No values are labelled this way until job 24521 runs.
- **[Calculated]**: arithmetic over a timestamped Slurm snapshot.
- **[Unknown]**: not exposed or not yet measured; no inference from hostnames is made.

## Executive summary

The cluster is `hpcwp`, running Slurm 24.11.6. Your account is `hpc`, QoS `normal`; you are in groups `stud` and `sit-hpc-geelong`. The GPU partition exposes 23 configured GPU nodes, 896 CPU slots, 4,360,000 MiB of scheduler memory and 51 GPUs. It includes 13 GPUs registered as `a100`, but all 13 were allocated when inspected, so neither an exact A100 hardware audit nor GPU benchmarks could run immediately.

You currently have two pending two-A100 jobs: the pre-existing audit (24517) and the newly submitted short diagnostic/benchmark (24521). Each requests one node, two `a100` GPUs, 8 CPUs, 32 GiB and 15 minutes. Slurm reported priority 1 and an estimated start of 2026-08-04 20:44 AEST for both. This is an estimate, not a reservation. The short benchmark job is designed to produce the missing measured data without downloading a model.

The current research checkout is healthy at the test level: `47 passed in 1.84s` in `/home/s224049759/environments/cmpilot-conda`. That environment contains Python 3.11.15 and pytest but no detected PyTorch/Transformers/vLLM packages, so it is not yet an inference environment.

## Login, identity and scheduler

| Item | Value | Evidence |
|---|---|---|
| Login hostname | `hpc` (`hostname -f` returned `hpc`) | [Measured on login] |
| Login OS | Ubuntu 22.04.5 LTS | [Measured on login] |
| Login kernel | Linux 5.15.0-186-generic x86_64 | [Measured on login] |
| Slurm | 24.11.6 | [Slurm] |
| LMOD | Modules based on Lua 6.6, dated 2016-10-13 | [Measured on login] |
| User / account / QoS | `s224049759` / `hpc` / `normal` | [Slurm] |
| Groups | `stud`, `sit-hpc-geelong` | [Measured on login] |
| Cluster | `hpcwp` | [Slurm] |
| Scheduler | `sched/backfill`; controller UP | [Slurm] |
| Priority configuration | multifactor with all configured weights shown as zero; each of your jobs displayed priority 1 | [Slurm] |

## Scheduler policy and your usable allocation

| Policy or limit | Value | Evidence |
|---|---|---|
| Partitions | `Virtual` (default) and `gpu` | [Slurm] |
| Virtual time limit | unlimited; default time none | [Slurm] |
| GPU time limit | maximum 7 days; default 5 days 1 hour | [Slurm] |
| GPU node limit | maximum 1 node/job | [Slurm] |
| Default GPU memory request | 4,000 MiB/CPU when memory is not requested | [Slurm] |
| Allocation model | `select/cons_tres`, `CR_CORE_MEMORY`: CPUs and memory are consumable resources | [Slurm] |
| Oversubscription | `OverSubscribe=NO` in both partitions | [Slurm] |
| Preemption | globally OFF; GPU partition OFF | [Slurm] |
| Requeue | global `JobRequeue=1` | [Slurm] |
| QoS concurrent jobs | `MaxJobsPU=2` | [Slurm] |
| QoS CPU limit | `MaxTRESPU=cpu=20,gres/+` exactly as printed by `sacctmgr` | [Slurm] |
| GPU / memory limit | no explicit typed GPU or memory maximum was printed for the association/QoS; `gres/+` needs administrator interpretation | [Unknown / admin-controlled] |
| Account association limits | none displayed | [Slurm] |
| Submission limit | none displayed (`MaxSubmitPU` blank) | [Slurm] |

`normal` has the `DenyOnLimit` flag. Consequently, stay within the demonstrated two concurrent jobs and 20 CPU limits. The `gres/+` text must not be treated as a confirmed per-user A100 entitlement.

### Current account state

At the snapshot, no resource was allocated to your account: both jobs had `AllocTRES=(null)` and were pending. Their aggregate request is 4 A100 GPUs, 16 CPUs and 64 GiB across two one-node jobs, subject to the scheduler and any undisclosed GPU limits. `sacct` returned no completed historical jobs for this user from 2020-01-01 onward; only 24517 and 24521 are present and pending.

| Job | State/reason | Request | Slurm estimated start |
|---|---|---|---|
| 24517 `compute-audit` | PENDING / Priority | 2 A100, 8 CPU, 32 GiB, 15 min | 2026-08-04 20:44:01 |
| 24521 `two-a100-diag` | PENDING / Priority | 2 A100, 8 CPU, 32 GiB, 15 min | 2026-08-04 20:44:01 |

## Shared cluster capacity

The table uses Slurm GRES labels, not assumed retail product names. CPU and RAM values are scheduler configuration values (MiB), not an in-job hardware measurement.

| GPU-node type (Slurm label) | Nodes | CPU slots | Scheduler RAM | GPUs |
|---|---:|---:|---:|---:|
| `g16-8gpu-1`: `rtxa4000` | 1 | 128 | 480,000 MiB | 8 |
| `g20-2gpu-*`: `rtxa4000ada` | 5 | 160 | 600,000 MiB | 10 |
| `g24-2gpu-*`: `rtx4500` | 3 | 192 | 480,000 MiB | 6 |
| `g32-2gpu-1`: `v100` | 1 | 40 | 80,000 MiB | 2 |
| `g40-*-gpu-*`: `a100` | 4 | 192 | 960,000 MiB | 13 |
| `g46-1gpu-*`, `g46-2gpu-*`: `l40s` | 6 | 64 | 1,280,000 MiB | 8 |
| `g48-*-gpu-*`: `rtx6000` | 3 | 120 | 480,000 MiB | 4 |
| **GPU partition total** | **23** | **896** | **4,360,000 MiB** | **51** |

Thus, there are 13 A100s, 8 L40S GPUs, 28 GPUs with an `rtx*` Slurm label, and 2 V100s. The configured `Virtual` partition separately reports 6 nodes, 36 CPUs and 126,000 MiB. Adding partition configuration produces a nominal 29 compute nodes, 932 CPU slots and 4,486,000 MiB, but live `sinfo` listed only five Virtual nodes (28 CPUs / 96,000 MiB). This configuration/live discrepancy requires administrator confirmation before claiming a full-cluster live CPU total.

### Live scheduler snapshot: 2026-08-02 17:11 AEST

[Calculated] from `AllocTRES` in `scontrol show node -o`:

| Resource | Configured GPU partition | Allocated | Not allocated |
|---|---:|---:|---:|
| CPU slots | 896 | 82 | 814 |
| Scheduler memory | 4,360,000 MiB | 759,296 MiB | 3,600,704 MiB |
| GPUs | 51 | 26 | 25 |
| A100 GPUs | 13 | 13 | 0 |
| L40S GPUs | 8 | 8 | 0 |
| RTX-labelled GPUs | 28 | 5 | 23 |
| V100 GPUs | 2 | 0 | 2 |

The memory “not allocated” figure is not equivalent to operating-system free RAM; it is scheduler capacity less allocated TRES. Node states were 10 idle, 10 mixed and 3 allocated in `gpu`; no unavailable GPU node was reported. The live Virtual output showed 5 idle nodes; its configured sixth node was not returned by `scontrol show node`.

These are shared resources, not your allocation. In particular, zero A100 GPUs were free at the instant sampled, while your current allocation was zero.

## A100, CPU and RAM hardware audit

Slurm confirms that the A100 nodes are one-node `gpu:a100` resources with 48 logical CPUs, one socket, 24 cores/socket, two threads/core and 240,000 MiB scheduler RAM. It does **not** expose the CPU model, A100 product SKU, VRAM, bus form factor, driver, PCIe link, SM count, MIG state, topology or NVLink.

Accordingly, the following are **unknown until job 24521 runs**: exact product name; PCIe versus SXM; usable VRAM; MIG; driver and supported CUDA version; compute capability; SM count; Tensor Core generation; memory type/bandwidth; power limit; maximum clocks; PCIe generation/width; GPU topology/NVLink link count; GPU-to-GPU path; CPU/GPU NUMA affinity; actual CPU model/cache/clocks and memory bandwidth. A host label such as `g40` was not used as evidence of 40 GiB VRAM.

The requested two-A100 allocation is valid (both 24517 and 24521 were accepted with `TresPerNode=gres/gpu:a100:2`), so Slurm permits both GPUs to be requested in one job. It does not prove a pair was available at collection time or establish physical interconnect topology.

## Storage

| Item | Value | Evidence |
|---|---|---|
| Home | `/home/s224049759` | [Measured on login] |
| Home filesystem | Ceph (`10.120.0.144, .145, .146:/`) | [Measured on login] |
| Filesystem capacity at snapshot | 1.7 PiB total, 595 TiB used, 1.1 PiB available (36%) | [Measured on login] |
| Home usage | 523 MiB | [Measured on login] |
| Personal quota | not exposed; `quota` is not installed | [Unknown] |
| Archive path | symlink target `/ceph-g/archive/s224049759` | [Measured on login] |
| Archive availability | target did not exist on the login node; usage/quota unavailable | [Measured on login] |
| Model cache | `/home/s224049759/model-cache`, existing and empty; no HF/Transformers cache environment variable set | [Measured on login] |
| `$TMPDIR` on login | unset | [Measured on login] |
| Login scratch directories | `/scratch`, `/local`, `/localscratch` absent; `/tmp` present | [Measured on login] |

Use the project directory for source and small reproducible artefacts. Use `/home/s224049759/model-cache` only after obtaining a personal-quota answer, and set `HF_HOME`/`TRANSFORMERS_CACHE` explicitly if it is selected. Use a job-local `$TMPDIR` or `/tmp` only for disposable, in-run data; its compute-node locality and capacity are pending the diagnostic. Do not rely on `~/archive` until the broken/unmounted archive target is resolved; use it for archived results only after administrator confirmation.

## Network and interconnect

The login host has `lo` and `eth0` (UP); no InfiniBand tools were installed there and no login-node NVIDIA utility was available. Link speed, InfiniBand availability, compute-node internet egress, NCCL transport and GPU peer path are all pending job 24521. The job tests `ip`, `ethtool`, `ibstat`, `ibv_devinfo`, a small HTTPS header request, `nvidia-smi topo -m`, NVLink status, P2P access/copy, and a two-rank NCCL all-reduce. No claim about compute-node internet access, NVLink or NCCL peer-to-peer is made before those results exist.

## Software stack

| Component | Verified availability |
|---|---|
| Python modules | 3.8, 3.9, 3.10, 3.11, 3.13 |
| Login default Python/Conda | Python 3.12.8; Conda 26.1.0 at `/opt/miniconda3` |
| User environment | `/home/s224049759/environments/cmpilot-conda`, Python 3.11.15, pytest 9.1.1; no detected ML packages |
| CUDA modules | 11.2, 12.2, 12.6 |
| PyTorch modules | 1.7.0/py3.8, 1.10.1/py3.9, 2.7.1/py3.13 |
| Candidate benchmark module | PyTorch 2.7.1 reports CUDA runtime 12.9 and cuDNN 91100; CUDA unavailable on the login node as expected |
| GCC/G++ | system 11.4.0; no `gcc` module found |
| NVIDIA tools/modules | `nvhpc/20.7`, Nsight Compute/Systems modules; `nvcc` absent until a CUDA/PyTorch module is loaded |
| Singularity / Apptainer | Singularity 3.6.0 / Apptainer absent |
| Git | 2.34.1 |
| CMake / Ninja | CMake path exists but fails for missing `libssl.so.1.1`; Ninja absent |
| Slurm commands | `srun`, `sbatch`, `squeue`, `sacct`, `scontrol` present |

Use `module purge && module load pytorch/2.7.1_py3.13` for the queued diagnostic. Do not combine it casually with `cuda/12.6`: the PyTorch module prepends its own `nvcc` 12.9, despite its metadata mentioning an older toolkit.

## Practical LLM capacity

No numerical “largest practical model” is asserted yet because the A100 VRAM/SKU and available runtime headroom are not measured. Raw-weight memory alone is insufficient: model execution additionally needs quantisation metadata, framework/CUDA allocator space, CUDA graphs, activations (training), and KV cache whose size depends on architecture, context, batch/concurrency and KV-head layout.

The following is a formula, not a hardware result. For a GPU with measured usable VRAM `V` GiB, an ideal raw-weight ceiling in billions of parameters is approximately:

| Weight format | Bytes/parameter | One GPU raw ceiling | Two GPUs raw ceiling |
|---|---:|---:|---:|
| FP32 | 4 | `0.268 × V` B | `0.537 × V` B |
| BF16 / FP16 | 2 | `0.537 × V` B | `1.074 × V` B |
| FP8 / INT8 | 1 | `1.074 × V` B | `2.147 × V` B |
| nominal 4-bit | 0.5 | `2.147 × V` B | `4.295 × V` B |

Practical inference ceilings are lower. Context-length recommendations for 7B, 14B, 24B, 30B, 32B and 70B cannot be responsibly computed from parameter count alone before `V`, model architecture and the benchmarked free memory are known. The completed job will establish the first two inputs (device VRAM and actual framework overhead); a chosen model then determines KV cache.

If the measured topology offers peer access and adequate inter-GPU bandwidth, two-GPU tensor parallelism can be tested with the queued NCCL all-reduce. vLLM, Transformers, LoRA/QLoRA and full fine-tuning recommendations remain conditional on those results and on installing a compatible ML environment. In general, two GPUs can support independent inference servers only when each server’s weights plus KV cache fit entirely within its allocated GPU; it should not be assumed before VRAM is measured. For coding-agent experiments, likely bottlenecks include queue delay for A100 pairs, per-user two-job/20-CPU limits, model-cache quota, unavailable archive storage, context/KV memory and tool/repository I/O—not the small test suite.

## Project readiness

The checkout is on `fix/portable-test-imports...origin/fix/portable-test-imports` at `47f2831`. Existing tracked work is a modified `pyproject.toml` and added `scripts/__init__.py`; `slurm/` was already untracked and the inventory directory is newly untracked output from this report. `git diff --check` was clean and no tracked ignored files were reported. `pytest -q` in the user environment passed 47/47 tests.

Before model inference: provision a separate pinned ML environment (do not contaminate the small test environment), select and configure the cache location, resolve archive/quota policy, wait for the A100 audit, and test the chosen model with a conservative KV-cache/concurrency setting. No large model was downloaded.

## Recommended requests and setup

Use the demonstrated conservative A100 request for topology-sensitive experiments:

```bash
#SBATCH --partition=gpu
#SBATCH --gres=gpu:a100:2
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=00:15:00
```

For ordinary one-GPU work, request the smallest GPU/CPU/memory/time combination that satisfies the task and name the GPU type explicitly. Keep the two-job / 20-CPU QoS bound in mind. For coding-agent research: start with one GPU and a small local model or API-compatible server after the audit; move to two-GPU tensor parallel only if the measured topology/NCCL test passes and the chosen model cannot fit per GPU. Keep source in the repository, cache explicitly in `~/model-cache` once quota is confirmed, write transient checkpoints into job-local temporary storage, and archive only after the archive mount is fixed.

## Missing information for administrators

1. Personal home and model-cache quota; intended quota for the broken `~/archive` target.
2. Why `/ceph-g/archive/s224049759` is absent on the login host, and the archive filesystem/capacity/quota.
3. The live state and capacity of configured `hpcwp-cpu6`.
4. Meaning of QoS `MaxTRESPU=cpu=20,gres/+`, especially any per-user typed GPU cap.
5. A100 hardware SKU/VRAM/topology/network details if job 24521 cannot run; the job itself will otherwise measure these.
6. Compute-node egress and any usage-policy restrictions for model downloads or inference services.

## Artefacts and commands

- `raw_cluster_inventory.txt`: combined raw output for login, Slurm, node, storage, software and project commands.
- `scheduler_limits.txt`: detailed association/QoS, priority and job history commands.
- `gpu_audit.txt`: inspection of the pre-existing job 24517.
- `storage_inventory.txt`, `software_inventory.txt`, `node_inventory.txt`, `project_readiness.txt`: focused raw inventories.
- `two_a100_diagnostic.sbatch`: exact commands for the accepted job 24521.
- `benchmark_results.txt`: pending-job snapshot and output locations.

The raw files include the requested commands verbatim, including `hostname -f`, `/etc/os-release`, `uname -a`, `scontrol version`, `sinfo`, `scontrol show partition/config`, `sacctmgr`, `sprio`, `squeue`, `sacct`, storage/module/software checks, and repository checks. The A100 script contains the requested `nvidia-smi`, topology/NVLink, `lscpu`, NUMA, Slurm environment and short PyTorch/NCCL benchmark commands.
