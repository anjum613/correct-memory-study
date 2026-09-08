#!/usr/bin/env bash
set -euo pipefail
SOURCE_SCRIPT=/tmp/guided-backend-fix.z67iAU/cpu-backend-gate.sbatch
ARTIFACT_DIR=/home/s224049759/run-artifacts/guided-backend-fix/${SLURM_JOB_ID}
/usr/bin/mkdir -p -- "$ARTIFACT_DIR"
/usr/bin/cp -- "$SOURCE_SCRIPT" "$ARTIFACT_DIR/cpu-backend-gate.sbatch"
exec >"$ARTIFACT_DIR/stdout.log" 2>"$ARTIFACT_DIR/stderr.log"
GUIDED_BACKEND_CHECK_STARTED=1
