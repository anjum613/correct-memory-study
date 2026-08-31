#!/usr/bin/bash
#SBATCH --job-name=devstral-final-lifecycle-smoke-v1
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
#SBATCH --gres=gpu:a100:2
#SBATCH --time=01:00:00
#SBATCH --no-requeue
#SBATCH --output=/home/s224049759/slurm-logs/devstral-final-lifecycle-smoke-v1-%j.out
#SBATCH --error=/home/s224049759/slurm-logs/devstral-final-lifecycle-smoke-v1-%j.err

set -euo pipefail
umask 077

PROJECT=/home/s224049759/projects/correct-memory-study-worktrees/track-b-mcp-pinot-v01
CONTROLLER_PYTHON=/home/s224049759/environments/cmpilot-conda/bin/python
ARTIFACT_ROOT=/home/s224049759/final-experiment-artifacts/devstral-final-lifecycle-prerun-smoke/v1

: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
test -x "$CONTROLLER_PYTHON"
test -f "$PROJECT/scripts/run_devstral_final_lifecycle_smoke.py"

export PYTHONDONTWRITEBYTECODE=1
export PYTHONNOUSERSITE=1
export HF_HUB_DISABLE_IMPLICIT_TOKEN=1
export HF_HUB_DISABLE_TELEMETRY=1
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export NO_PROXY=127.0.0.1,localhost
export no_proxy=127.0.0.1,localhost
unset HF_TOKEN HUGGING_FACE_HUB_TOKEN

exec "$CONTROLLER_PYTHON" \
    "$PROJECT/scripts/run_devstral_final_lifecycle_smoke.py" \
    --artifact-root "$ARTIFACT_ROOT"
