#!/usr/bin/bash
set -euo pipefail
PRE_SUBMIT=/home/s224049759/run-artifacts/qwen32b-load-gate/pre-submit-20260806T072036Z
SOURCE_SCRIPT=$PRE_SUBMIT/gpu-load-gate.sbatch
: "${SUBMITTED_SCRIPT_SHA256:?SUBMITTED_SCRIPT_SHA256 must be exported by sbatch}"

actual_script_sha256=$(/usr/bin/sha256sum -- "$SOURCE_SCRIPT")
actual_script_sha256=${actual_script_sha256%% *}
if [[ "$actual_script_sha256" != "$SUBMITTED_SCRIPT_SHA256" ]]; then
    /usr/bin/printf '{"label":"QWEN32B_LOAD_GATE_PRECONDITION_FAIL","message":"submitted script hash mismatch"}\n' \
        > "$ARTIFACT_DIR/result.json"
    exit 71
fi

# This copy was after the failed comparison and was not reached in job 25371.
/usr/bin/cp -- "$SOURCE_SCRIPT" "$ARTIFACT_DIR/submitted-load-gate.sbatch"

# The failed implementation did not preserve either comparison operand.
# CUDA, NCCL, vLLM, model loading, and endpoint checks followed later.
