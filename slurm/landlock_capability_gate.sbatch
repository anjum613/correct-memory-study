#!/usr/bin/bash
#SBATCH --job-name=git-boundary-landlock-gate-v1
#SBATCH --partition=Virtual
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=00:05:00
#SBATCH --no-requeue
#SBATCH --output=/home/s224049759/slurm-logs/git-boundary-landlock-gate-v1-%j.out
#SBATCH --error=/home/s224049759/slurm-logs/git-boundary-landlock-gate-v1-%j.err

set -euo pipefail
umask 077

PROJECT=/home/s224049759/projects/worktrees/git-boundary-hardening-v1
PYTHON=/home/s224049759/environments/cmpilot-conda/bin/python
PROBE="$PROJECT/scripts/landlock_capability_probe.py"
SOURCE_BATCH="$PROJECT/slurm/landlock_capability_gate.sbatch"
ARTIFACT_ROOT=/home/s224049759/run-artifacts/git-boundary-hardening/v1/landlock-capability-gate/jobs
ARTIFACT_DIR="$ARTIFACT_ROOT/$SLURM_JOB_ID"

/usr/bin/mkdir -p -- "$ARTIFACT_DIR"
/usr/bin/cp -- "$SOURCE_BATCH" "$ARTIFACT_DIR/source-batch-script.sbatch"
/usr/bin/cp -- "$0" "$ARTIFACT_DIR/submitted-batch-script.sbatch"
/usr/bin/cp -- "$PROBE" "$ARTIFACT_DIR/landlock-capability-probe.py"
/usr/bin/sha256sum -- \
    "$ARTIFACT_DIR/source-batch-script.sbatch" \
    "$ARTIFACT_DIR/submitted-batch-script.sbatch" \
    "$ARTIFACT_DIR/landlock-capability-probe.py" \
    > "$ARTIFACT_DIR/input-sha256.txt"

set +e
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" "$PROBE" \
    --output "$ARTIFACT_DIR/result.json" \
    --scratch-parent /tmp \
    --batch-script "$ARTIFACT_DIR/submitted-batch-script.sbatch"
PROBE_EXIT=$?
set -e

/usr/bin/printf '%s\n' "$PROBE_EXIT" > "$ARTIFACT_DIR/probe-exit-code.txt"
/usr/bin/sha256sum -- "$ARTIFACT_DIR"/* > "$ARTIFACT_DIR/SHA256SUMS"
exit "$PROBE_EXIT"
