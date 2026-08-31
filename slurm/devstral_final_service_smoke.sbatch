#!/usr/bin/bash
#SBATCH --job-name=devstral-final-service-smoke-v1
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=128G
#SBATCH --gres=gpu:a100:2
#SBATCH --time=01:00:00
#SBATCH --no-requeue
#SBATCH --output=/home/s224049759/slurm-logs/devstral-final-service-smoke-v1-%j.out
#SBATCH --error=/home/s224049759/slurm-logs/devstral-final-service-smoke-v1-%j.err

set -euo pipefail
umask 077

PROJECT=${1:?project worktree is required}
CONTROLLER_PY=${2:?controller Python is required}
EXPECTED_COMMIT=${3:?expected project commit is required}
ARTIFACT_ROOT=${4:?artifact root is required}
ATTEMPT_DIR="$ARTIFACT_ROOT/slurm-$SLURM_JOB_ID-service-smoke-v1"
PREFLIGHT_RECORD="$ARTIFACT_ROOT/slurm-$SLURM_JOB_ID-service-smoke-v1.preflight.json"
STDOUT_RECORD="$ARTIFACT_ROOT/slurm-$SLURM_JOB_ID-service-smoke-v1.stdout.json"
STDERR_RECORD="$ARTIFACT_ROOT/slurm-$SLURM_JOB_ID-service-smoke-v1.stderr"

mkdir -p "$ARTIFACT_ROOT"
test -x "$CONTROLLER_PY"
test -x /usr/bin/nvidia-smi
test -n "${CUDA_VISIBLE_DEVICES:-}"
test -f "$PROJECT/scripts/devstral_final_service_smoke.py"
test ! -e "$ATTEMPT_DIR"
test ! -L "$ATTEMPT_DIR"
test ! -e "$PREFLIGHT_RECORD"
test ! -L "$PREFLIGHT_RECORD"
test ! -e "$STDOUT_RECORD"
test ! -L "$STDOUT_RECORD"
test ! -e "$STDERR_RECORD"
test ! -L "$STDERR_RECORD"

cleanup_server_fallback() {
    local pid=
    local state=
    if [ ! -f "$ATTEMPT_DIR/server.pid" ]; then
        return 0
    fi
    if [ -f "$ATTEMPT_DIR/server-shutdown.json" ] && \
        /usr/bin/jq -e '.pass == true and (.process.returncode != null)' \
            "$ATTEMPT_DIR/server-shutdown.json" >/dev/null; then
        return 0
    fi
    pid=$(sed -n '1p' "$ATTEMPT_DIR/server.pid")
    if ! [[ "$pid" =~ ^[0-9]+$ ]]; then
        return 1
    fi
    state=$(/usr/bin/ps -o stat= -p "$pid" 2>/dev/null || true)
    state=${state:0:1}
    if [ -n "$state" ] && [ "$state" != Z ]; then
        kill -TERM -- "-$pid" 2>/dev/null || true
        for _ in $(seq 1 30); do
            if ! kill -0 "$pid" 2>/dev/null; then
                break
            fi
            sleep 1
        done
        if kill -0 "$pid" 2>/dev/null; then
            kill -KILL -- "-$pid" 2>/dev/null || true
        fi
    fi
}

on_exit() {
    local status=$?
    set +e
    cleanup_server_fallback || status=1
    if [ -d "$ATTEMPT_DIR" ]; then
        /usr/bin/nvidia-smi --query-gpu=index,name,memory.used \
            --format=csv,noheader,nounits \
            > "$ATTEMPT_DIR/gpu-memory-after-shutdown.csv" 2>&1 || status=1
    fi
    trap - EXIT
    exit "$status"
}
trap on_exit EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

"$CONTROLLER_PY" "$PROJECT/scripts/devstral_final_service_smoke.py" \
    --attempt-directory "$ATTEMPT_DIR" \
    --expected-project-commit "$EXPECTED_COMMIT" \
    --job-id "$SLURM_JOB_ID" \
    --preflight-only > "$PREFLIGHT_RECORD"

"$CONTROLLER_PY" "$PROJECT/scripts/devstral_final_service_smoke.py" \
    --attempt-directory "$ATTEMPT_DIR" \
    --expected-project-commit "$EXPECTED_COMMIT" \
    --job-id "$SLURM_JOB_ID" \
    > "$STDOUT_RECORD" 2> "$STDERR_RECORD"
