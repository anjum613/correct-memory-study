#!/usr/bin/bash
#SBATCH --job-name=cmpilot-final-array
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
#SBATCH --gres=gpu:a100:2
#SBATCH --time=00:45:00
#SBATCH --no-requeue
#SBATCH --output=/home/s224049759/slurm-logs/cmpilot-final-%A_%a.out
#SBATCH --error=/home/s224049759/slurm-logs/cmpilot-final-%A_%a.err

set -euo pipefail
umask 077

if [ "$#" -ne 11 ]; then
    printf 'expected 11 frozen submission operands, received %s\n' "$#" >&2
    exit 2
fi

PROJECT=$1
CONTROLLER_PYTHON=$2
RUNNER=$3
MANIFEST=$4
MANIFEST_SHA256=$5
MATRIX=$6
MATRIX_SHA256=$7
PLAN=$8
PLAN_SHA256=$9
RUN_ROOT=${10}
MODEL_PROFILE=${11}

: "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
: "${SLURM_ARRAY_TASK_ID:?SLURM_ARRAY_TASK_ID is required}"

test -x "$CONTROLLER_PYTHON"
test -f "$PROJECT/scripts/submit_final_experiment.py"
test -f "$RUNNER"
test -f "$MANIFEST"
test -f "$MATRIX"
test -f "$PLAN"

RUN_ID=$(
    "$CONTROLLER_PYTHON" "$PROJECT/scripts/submit_final_experiment.py" select-run \
        "$PLAN" \
        --expected-plan-sha256 "$PLAN_SHA256" \
        --model-profile "$MODEL_PROFILE" \
        --array-index "$SLURM_ARRAY_TASK_ID"
)
test -n "$RUN_ID"

exec "$CONTROLLER_PYTHON" "$RUNNER" \
    --manifest "$MANIFEST" \
    --expected-manifest-sha256 "$MANIFEST_SHA256" \
    --matrix "$MATRIX" \
    --expected-matrix-sha256 "$MATRIX_SHA256" \
    --run-root "$RUN_ROOT" \
    --run-id "$RUN_ID" \
    --job-id "$SLURM_JOB_ID" \
    --attempt-id "slurm-$SLURM_JOB_ID-$SLURM_ARRAY_TASK_ID"
