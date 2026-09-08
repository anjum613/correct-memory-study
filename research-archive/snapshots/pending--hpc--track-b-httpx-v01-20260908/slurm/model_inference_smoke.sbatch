#!/usr/bin/env bash
#SBATCH --job-name=model-smoke-1
#SBATCH --partition=gpu
#SBATCH --gres=gpu:rtxa4000ada:1
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=24G
#SBATCH --time=00:20:00
#SBATCH --output=/home/s224049759/slurm-logs/model-inference-smoke-%j.out
#SBATCH --error=/home/s224049759/slurm-logs/model-inference-smoke-%j.err

set -euo pipefail

PROJECT=/home/s224049759/projects/correct-memory-study
VENV=/home/s224049759/environments/model-smoke-transformers
ARTIFACT_ROOT=/home/s224049759/run-artifacts/model-smoke-1
ARTIFACT_DIR="$ARTIFACT_ROOT/$SLURM_JOB_ID"

mkdir -p "$ARTIFACT_DIR"
exec > >(tee -a "$ARTIFACT_DIR/stdout.txt") 2> >(tee -a "$ARTIFACT_DIR/stderr.txt" >&2)

record_exit() {
    status=$?
    date --iso-8601=seconds > "$ARTIFACT_DIR/finished_at.txt"
    printf '%s\n' "$status" > "$ARTIFACT_DIR/exit_status.txt"
}
trap record_exit EXIT

date --iso-8601=seconds > "$ARTIFACT_DIR/started_at.txt"
hostname -f > "$ARTIFACT_DIR/hostname.txt"
git -C "$PROJECT" rev-parse HEAD > "$ARTIFACT_DIR/git_commit.txt"
git -C "$PROJECT" --no-pager status --short --branch > "$ARTIFACT_DIR/git_status.txt"

env | awk -F= '
    /^(SLURM|CUDA|NVIDIA_|HF_|TOKENIZERS_)/ {
        if ($1 ~ /(TOKEN|SECRET|PASSWORD|API_KEY)/) {
            print $1 "=[REDACTED]"
        } else {
            print
        }
    }
' | sort > "$ARTIFACT_DIR/slurm_environment.txt"

module purge
module load pytorch/2.7.1_py3.13
module list > "$ARTIFACT_DIR/module_list.txt" 2>&1

export HF_HOME=/home/s224049759/model-cache/huggingface
export HF_HUB_DISABLE_TELEMETRY=1
export TOKENIZERS_PARALLELISM=false
export PYTHONPATH="$PROJECT/src"

mkdir -p "$HF_HOME"
nvidia-smi > "$ARTIFACT_DIR/nvidia-smi.txt"
nvidia-smi topo -m > "$ARTIFACT_DIR/nvidia-smi-topology.txt"
"$VENV/bin/python" -m pip freeze | sort > "$ARTIFACT_DIR/pip-freeze.txt"
printf '%q ' "$VENV/bin/python" "$PROJECT/scripts/model_inference_smoke.py" \
    --artifact-dir "$ARTIFACT_DIR" --model-id Qwen/Qwen2.5-Coder-1.5B-Instruct \
    > "$ARTIFACT_DIR/command.txt"
printf '\n' >> "$ARTIFACT_DIR/command.txt"

"$VENV/bin/python" "$PROJECT/scripts/model_inference_smoke.py" \
    --artifact-dir "$ARTIFACT_DIR" \
    --model-id Qwen/Qwen2.5-Coder-1.5B-Instruct

du -sh "$HF_HOME" > "$ARTIFACT_DIR/model-cache-size.txt"
