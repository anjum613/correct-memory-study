#!/usr/bin/env bash
#SBATCH --job-name=gpu-smoke-0
#SBATCH --partition=gpu
#SBATCH --gres=gpu:rtxa4000ada:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=00:05:00
#SBATCH --output=/home/s224049759/slurm-logs/gpu-smoke-%j.out
#SBATCH --error=/home/s224049759/slurm-logs/gpu-smoke-%j.err

set -euo pipefail

project_root=/home/s224049759/projects/correct-memory-study
artifact_root=/home/s224049759/run-artifacts/smoke-0
job_id=${SLURM_JOB_ID:?SLURM_JOB_ID is required}
artifact_dir="$artifact_root/$job_id"
mkdir -p "$artifact_dir"

exec > >(tee "$artifact_dir/stdout.txt") 2> >(tee "$artifact_dir/stderr.txt" >&2)
started_at=$(date --iso-8601=seconds)
finish() {
    exit_code=$?
    finished_at=$(date --iso-8601=seconds)
    {
        printf 'started_at=%s\n' "$started_at"
        printf 'finished_at=%s\n' "$finished_at"
        printf 'exit_code=%s\n' "$exit_code"
    } > "$artifact_dir/timestamps.txt"
    exit "$exit_code"
}
trap finish EXIT

printf 'GPU smoke job %s started on %s at %s\n' "$job_id" "$(hostname -f)" "$started_at"
printf '%s\n' "$job_id" > "$artifact_dir/job-id.txt"
hostname -f > "$artifact_dir/hostname.txt"
(
    cd "$project_root"
    git rev-parse HEAD
) > "$artifact_dir/git-commit.txt"
(
    cd "$project_root"
    git status --short --branch
) > "$artifact_dir/git-status.txt"

module purge
module load pytorch/2.7.1_py3.13
module list 2>&1 | tee "$artifact_dir/module-list.txt"
env | grep -E '^(SLURM|CUDA|NVIDIA_)' | sort > "$artifact_dir/slurm-environment.txt"
set +e
nvidia-smi | tee "$artifact_dir/nvidia-smi.txt"
nvidia_smi_status=${PIPESTATUS[0]}
nvidia-smi topo -m | tee "$artifact_dir/nvidia-smi-topology.txt"
nvidia_topology_status=${PIPESTATUS[0]}
set -e
printf "nvidia_smi_exit_status=%s\nnvidia_topology_exit_status=%s\n" "$nvidia_smi_status" "$nvidia_topology_status" > "$artifact_dir/nvidia-smi-exit-status.txt"

export PYTHONPATH="$project_root/src${PYTHONPATH:+:$PYTHONPATH}"
printf '%s\n' "python=$(command -v python)" > "$artifact_dir/python-command.txt"
python "$project_root/scripts/gpu_smoke.py" --artifact-dir "$artifact_dir"
printf 'GPU smoke job %s finished successfully at %s\n' "$job_id" "$(date --iso-8601=seconds)"
