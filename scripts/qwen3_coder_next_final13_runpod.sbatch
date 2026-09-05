#!/usr/bin/env bash
#SBATCH --job-name=qwen3-next-tools-final13
#SBATCH --partition=Virtual
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=12G
#SBATCH --time=24:00:00
#SBATCH --output=slurm-%x-%j.out

set -euo pipefail
cd "${SLURM_SUBMIT_DIR:?Submit this file from the project root}"
exec scripts/run_qwen3_coder_next_final13_hpc.sh
