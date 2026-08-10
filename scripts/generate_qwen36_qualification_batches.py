#!/usr/bin/env python3
"""Render the seven attested Qwen3.6 no-memory qualification batches."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.qwen36_candidate import MODEL_REVISION, sha256_file  # noqa: E402
from cmpilot.qwen36_qualification import (  # noqa: E402
    ALL_TASKS,
    PRIMARY_TASKS,
    QUALIFICATION_FREEZE,
    SEED_SCHEDULE,
    validate_seed_schedule,
)
from cmpilot.qwen36_submission_gate import (  # noqa: E402
    batch_gate_equivalence,
    validate_submission_gate,
)


OUTPUTS = {
    task_id: ROOT / "slurm" / f"qwen36_{task_id.replace('-', '_')}.sbatch"
    for task_id in ALL_TASKS
}
TECHNICAL_RERUN_TASK = "qnm-p01-interval-merge"
TECHNICAL_RERUN_OF = "26036"
TECHNICAL_RERUN_NUMBER = 1
TECHNICAL_ROOT_QUALIFICATION = "25953"
TECHNICAL_RERUN_OUTPUT = (
    ROOT / "slurm/qwen36_qnm_p01_interval_merge_technical_rerun_26036_1.sbatch"
)


TEMPLATE = r'''#!/usr/bin/bash
#SBATCH --job-name=@@JOB_NAME@@
#SBATCH --partition=gpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=192G
#SBATCH --gres=gpu:a100:2
#SBATCH --time=03:00:00
#SBATCH --no-requeue
#SBATCH --output=/home/s224049759/slurm-logs/@@JOB_NAME@@-%j.out
#SBATCH --error=/home/s224049759/slurm-logs/@@JOB_NAME@@-%j.err

set -euo pipefail

PROJECT=/home/s224049759/projects/worktrees/qwen32b-protocol-hardening
CMPILOT_PY=/home/s224049759/environments/cmpilot-conda/bin/python
MINI_PY=/home/s224049759/environments/mini-swe-agent-smoke/bin/python
VLLM_PY=/home/s224049759/environments/qwen36-vllm-v1/bin/python
MODEL_ID=Qwen/Qwen3.6-27B
MODEL_REVISION=6a9e13bd6fc8f0983b9b99948120bc37f49c13e9
MODEL=/home/s224049759/model-cache/huggingface/hub/models--Qwen--Qwen3.6-27B/snapshots/$MODEL_REVISION
MODEL_CACHE=/home/s224049759/model-cache/huggingface
TASK_ID=@@TASK_ID@@
TASK_SEED=@@TASK_SEED@@
TASK_ROLE=@@TASK_ROLE@@
@@TECHNICAL_RERUN_METADATA@@
SUITE=$PROJECT/qualification/qwen32b-v1/suite-manifest.json
SUITE_REFERENCE=$PROJECT/qualification/qwen36-v1/suite-reference.json
TASK=$PROJECT/qualification/qwen32b-v1/tasks/$TASK_ID.json
FREEZE=$PROJECT/qualification/qwen36-v1/qualification-freeze-manifest.json
EXPECTED_FREEZE_SHA256=@@FREEZE_SHA256@@
SEED_SCHEDULE=$PROJECT/qualification/qwen36-v1/qualification-seeds.json
EXPECTED_SEED_SCHEDULE_SHA256=@@SEED_SCHEDULE_SHA256@@
INFRASTRUCTURE_AMENDMENT=$PROJECT/@@AMENDMENT_PATH@@
EXPECTED_AMENDMENT_SHA256=@@AMENDMENT_SHA256@@
AGENT_CONFIG_SOURCE=$PROJECT/qualification/qwen36-v1/qualification-agent-config.json
SUBMISSION_GATE_RECORD=$PROJECT/@@SUBMISSION_GATE_PATH@@
EXPECTED_SUBMISSION_GATE_SHA256=@@SUBMISSION_GATE_SHA256@@
CPU_GATE=@@CPU_GATE@@
EXPECTED_CPU_GATE_SHA256=@@CPU_GATE_SHA256@@
EXPECTED_SUITE_REFERENCE_SHA256=@@SUITE_REFERENCE_SHA256@@
ENV_FINGERPRINT=$PROJECT/qualification/qwen36-v1/environment-fingerprint.json
ENV_CONTENT=$PROJECT/qualification/qwen36-v1/environment-content-digest.json
ARTIFACT_ROOT=/home/s224049759/run-artifacts/qwen36-no-memory-qualification/v1/tasks/$TASK_ID/jobs
ARTIFACT_DIR=$ARTIFACT_ROOT/$SLURM_JOB_ID
RUN_ARTIFACT=$ARTIFACT_DIR/run
RUNTIME_SCRATCH=/tmp/cmq-$SLURM_JOB_ID
PORT_HELPER=$PROJECT/scripts/qwen36_server_port.py
SERVER_LIFECYCLE_HELPER=$PROJECT/scripts/qwen36_server_lifecycle.py
MAX_SERVER_BIND_ATTEMPTS=4
PORT_LOCK_ROOT=/tmp/cmq-qwen36-$UID-ports
PORT=
BASE_URL=
PORT_LOCK_FD=
PORT_LOCK_FILE=
SERVER_PID=

mkdir -p "$ARTIFACT_DIR"

cleanup_server() {
    local shutdown_status=0
    if [ -z "$SERVER_PID" ]; then
        if [ -f "$ARTIFACT_DIR/server-shutdown.exit" ]; then
            return "$(cat "$ARTIFACT_DIR/server-shutdown.exit")"
        fi
        printf '0\n' > "$ARTIFACT_DIR/server-shutdown.exit"
        return 0
    fi
    "$CMPILOT_PY" "$SERVER_LIFECYCLE_HELPER" shutdown \
        --pid "$SERVER_PID" \
        --term-timeout-seconds 30 \
        --kill-timeout-seconds 10 \
        --record "$ARTIFACT_DIR/server-shutdown-result.json" \
        > "$ARTIFACT_DIR/server-shutdown.stdout" \
        2> "$ARTIFACT_DIR/server-shutdown.stderr" || shutdown_status=$?
    if [ "$shutdown_status" -eq 0 ]; then
        wait "$SERVER_PID" 2>/dev/null || true
    fi
    SERVER_PID=
    printf '%s\n' "$shutdown_status" > "$ARTIFACT_DIR/server-shutdown.exit"
    return "$shutdown_status"
}

release_port_claim() {
    local release_status=0
    if [ -n "$PORT_LOCK_FD" ]; then
        if [ -n "$PORT_LOCK_FILE" ]; then
            /usr/bin/rm -f -- "$PORT_LOCK_FILE" || release_status=1
        fi
        exec {PORT_LOCK_FD}>&- || release_status=1
    fi
    PORT_LOCK_FD=
    PORT_LOCK_FILE=
    return "$release_status"
}

cleanup_scratch() {
    "$CMPILOT_PY" "$PROJECT/scripts/qualification_runtime_path.py" cleanup \
        --job-id "$SLURM_JOB_ID" \
        --runtime-path "$RUNTIME_SCRATCH" \
        --record "$ARTIFACT_DIR/runtime-scratch-cleanup.json"
}

on_exit() {
    local primary_status=$?
    local server_status=0
    local port_status=0
    local scratch_status=0
    local gpu_status=0
    local manifest_status=0
    local final_status=$primary_status
    trap - EXIT TERM INT
    set +e
    cleanup_server
    server_status=$?
    release_port_claim
    port_status=$?
    cleanup_scratch
    scratch_status=$?
    /usr/bin/nvidia-smi > "$ARTIFACT_DIR/nvidia-smi-final.txt" 2>&1
    gpu_status=$?
    if [ "$final_status" -eq 0 ] && \
       { [ "$server_status" -ne 0 ] || [ "$port_status" -ne 0 ] || \
         [ "$scratch_status" -ne 0 ] || [ "$gpu_status" -ne 0 ]; }; then
        final_status=2
    fi
    printf '%s\n' "$primary_status" > "$ARTIFACT_DIR/batch-primary-exit-code.txt"
    printf '%s\n' "$final_status" > "$ARTIFACT_DIR/batch-exit-code.txt"
    printf '%s\n' "$final_status" > "$ARTIFACT_DIR/job-exit-code.txt"
    printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$ARTIFACT_DIR/job-finished-utc.txt"
    "$CMPILOT_PY" "$SERVER_LIFECYCLE_HELPER" record-status \
        --runner-exit-file "$ARTIFACT_DIR/qualification-runner.exit" \
        --server-shutdown-exit "$server_status" \
        --port-release-exit "$port_status" \
        --scratch-cleanup-exit "$scratch_status" \
        --gpu-final-exit "$gpu_status" \
        --manifest-exit -1 \
        --batch-exit "$final_status" \
        --record "$ARTIFACT_DIR/outer-finalizer-result.json" \
        > "$ARTIFACT_DIR/outer-finalizer.stdout" 2> "$ARTIFACT_DIR/outer-finalizer.stderr" || true
    "$CMPILOT_PY" "$PROJECT/scripts/qualification_job_manifest.py" "$ARTIFACT_DIR"
    manifest_status=$?
    if [ "$manifest_status" -ne 0 ] && [ "$final_status" -eq 0 ]; then final_status=2; fi
    printf '%s\n' "$manifest_status" > "$ARTIFACT_DIR/artifact-manifest.exit"
    printf '%s\n' "$final_status" > "$ARTIFACT_DIR/batch-exit-code.txt"
    printf '%s\n' "$final_status" > "$ARTIFACT_DIR/job-exit-code.txt"
    "$CMPILOT_PY" "$SERVER_LIFECYCLE_HELPER" record-status \
        --runner-exit-file "$ARTIFACT_DIR/qualification-runner.exit" \
        --server-shutdown-exit "$server_status" \
        --port-release-exit "$port_status" \
        --scratch-cleanup-exit "$scratch_status" \
        --gpu-final-exit "$gpu_status" \
        --manifest-exit "$manifest_status" \
        --batch-exit "$final_status" \
        --record "$ARTIFACT_DIR/outer-finalizer-result.json" \
        > "$ARTIFACT_DIR/outer-finalizer.stdout" 2> "$ARTIFACT_DIR/outer-finalizer.stderr" || true
    "$CMPILOT_PY" "$PROJECT/scripts/qualification_job_manifest.py" "$ARTIFACT_DIR"
    if [ "$?" -ne 0 ] && [ "$final_status" -eq 0 ]; then
        final_status=2
        printf '%s\n' "$final_status" > "$ARTIFACT_DIR/batch-exit-code.txt"
        printf '%s\n' "$final_status" > "$ARTIFACT_DIR/job-exit-code.txt"
    fi
    exit "$final_status"
}
trap on_exit EXIT
trap 'exit 143' TERM
trap 'exit 130' INT

test -x "$CMPILOT_PY"
test -x "$MINI_PY"
test -x "$VLLM_PY"
test -d "$MODEL"
test -f "$CPU_GATE"
test -f "$SUITE"
test -f "$SUITE_REFERENCE"
test -f "$TASK"
test -f "$FREEZE"
test -f "$SEED_SCHEDULE"
test -f "$INFRASTRUCTURE_AMENDMENT"
test -f "$AGENT_CONFIG_SOURCE"
test -f "$SUBMISSION_GATE_RECORD"
test "$(sha256sum "$FREEZE" | cut -d' ' -f1)" = "$EXPECTED_FREEZE_SHA256"
test "$(sha256sum "$SEED_SCHEDULE" | cut -d' ' -f1)" = "$EXPECTED_SEED_SCHEDULE_SHA256"
test "$(sha256sum "$SUITE_REFERENCE" | cut -d' ' -f1)" = "$EXPECTED_SUITE_REFERENCE_SHA256"
test "$(sha256sum "$INFRASTRUCTURE_AMENDMENT" | cut -d' ' -f1)" = "$EXPECTED_AMENDMENT_SHA256"
test "$(sha256sum "$SUBMISSION_GATE_RECORD" | cut -d' ' -f1)" = "$EXPECTED_SUBMISSION_GATE_SHA256"
test "$(sha256sum "$CPU_GATE" | cut -d' ' -f1)" = "$EXPECTED_CPU_GATE_SHA256"

"$CMPILOT_PY" - "$SUBMISSION_GATE_RECORD" "$CPU_GATE" "$TASK_ID" "$TASK_SEED" <<'PY'
import json
import sys
from pathlib import Path
gate = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
record = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
if gate.get("status") != "PASS":
    raise SystemExit("canonical submission gate is not PASS")
if gate.get("cpu_gate_result", {}).get("path") != sys.argv[2]:
    raise SystemExit("batch CPU gate differs from canonical submission gate")
if record.get("overall") != "PASS" or not all(record.get("checks", {}).values()):
    raise SystemExit("Qwen3.6 post-freeze CPU gate is not PASS")
if record.get("seeds", {}).get(sys.argv[3]) != int(sys.argv[4]):
    raise SystemExit("task seed differs from CPU-gated schedule")
if record.get("infrastructure_amendment_sha256") != "@@AMENDMENT_SHA256@@":
    raise SystemExit("CPU gate covered a different infrastructure amendment")
if record.get("qualification_freeze_sha256") != "@@FREEZE_SHA256@@":
    raise SystemExit("CPU gate covered a different scientific freeze")
if record.get("suite_reference_sha256") != "@@SUITE_REFERENCE_SHA256@@":
    raise SystemExit("CPU gate covered a different suite reference")
PY

git -C "$PROJECT" rev-parse HEAD > "$ARTIFACT_DIR/project-commit.txt"
git -C "$PROJECT" status --porcelain > "$ARTIFACT_DIR/project-status.txt"
test ! -s "$ARTIFACT_DIR/project-status.txt"
git -C "$PROJECT" rev-list -n 1 qwen32b-qualification-v1 > "$ARTIFACT_DIR/qwen32b-freeze-tag-target.txt"
test "$(sed -n '1p' "$ARTIFACT_DIR/qwen32b-freeze-tag-target.txt")" = ba039a0eaddc358d6b7174260c3b3c36169c44c0
sha256sum "$0" "$SUITE" "$SUITE_REFERENCE" "$TASK" "$FREEZE" \
    "$SEED_SCHEDULE" "$INFRASTRUCTURE_AMENDMENT" "$AGENT_CONFIG_SOURCE" \
    "$SUBMISSION_GATE_RECORD" "$CPU_GATE" \
    "$PORT_HELPER" "$SERVER_LIFECYCLE_HELPER" \
    > "$ARTIFACT_DIR/runtime-input-hashes.txt"
printf '%s\n' "$TASK_ID" > "$ARTIFACT_DIR/task-id.txt"
printf '%s\n' "$TASK_ROLE" > "$ARTIFACT_DIR/task-role.txt"
printf '%s\n' "$TASK_SEED" > "$ARTIFACT_DIR/task-seed.txt"
@@TECHNICAL_RERUN_ARTIFACTS@@
printf '%s\n' "$MODEL_ID" > "$ARTIFACT_DIR/model-id.txt"
printf '%s\n' "$MODEL_REVISION" > "$ARTIFACT_DIR/model-revision.txt"
printf '%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$ARTIFACT_DIR/job-started-utc.txt"
hostname > "$ARTIFACT_DIR/hostname.txt"
env | grep '^SLURM_' | LC_ALL=C sort > "$ARTIFACT_DIR/slurm-environment.txt"
/usr/bin/nvidia-smi > "$ARTIFACT_DIR/nvidia-smi-initial.txt"
/usr/bin/nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader,nounits \
    > "$ARTIFACT_DIR/gpu-allocation.csv"

export HF_HOME="$MODEL_CACHE"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export HF_HUB_DISABLE_TELEMETRY=1
export TOKENIZERS_PARALLELISM=false
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export NO_PROXY=127.0.0.1,localhost
export no_proxy=127.0.0.1,localhost

"$CMPILOT_PY" "$PROJECT/scripts/qualification_runtime_path.py" validate \
    --job-id "$SLURM_JOB_ID" \
    --task-id "$TASK_ID" \
    --persistent-artifact-root "$ARTIFACT_ROOT" \
    --runtime-path "$RUNTIME_SCRATCH" \
    --record "$ARTIFACT_DIR/runtime-ipc-path-budget.json"
"$CMPILOT_PY" "$PROJECT/scripts/qualification_runtime_path.py" prepare \
    --job-id "$SLURM_JOB_ID" \
    --runtime-path "$RUNTIME_SCRATCH" \
    --record "$ARTIFACT_DIR/runtime-scratch-preparation.json"
export TMPDIR="$RUNTIME_SCRATCH"
export TEMP="$RUNTIME_SCRATCH"
export TMP="$RUNTIME_SCRATCH"
export VLLM_RPC_BASE_PATH="$RUNTIME_SCRATCH"
printf 'TMPDIR=%s\nTEMP=%s\nTMP=%s\nVLLM_RPC_BASE_PATH=%s\n' \
    "$TMPDIR" "$TEMP" "$TMP" "$VLLM_RPC_BASE_PATH" \
    > "$ARTIFACT_DIR/runtime-environment.txt"

"$VLLM_PY" "$PROJECT/scripts/verify_qwen36_environment.py" \
    --output-directory "$ARTIFACT_DIR/environment-verification" \
    --expected-fingerprint "$ENV_FINGERPRINT" \
    --expected-content "$ENV_CONTENT" \
    > "$ARTIFACT_DIR/environment-verification.stdout" \
    2> "$ARTIFACT_DIR/environment-verification.stderr"

"$CMPILOT_PY" "$PORT_HELPER" schedule \
    --job-id "$SLURM_JOB_ID" \
    --record "$ARTIFACT_DIR/server-port-schedule.json" \
    > "$ARTIFACT_DIR/server-port-helper.stdout"
: > "$ARTIFACT_DIR/server-port-attempts.jsonl"
/usr/bin/install -d -m 700 "$PORT_LOCK_ROOT"

server_selected=0
for attempt in $(seq 1 "$MAX_SERVER_BIND_ATTEMPTS"); do
    PORT=$("$CMPILOT_PY" "$PORT_HELPER" candidate \
        --job-id "$SLURM_JOB_ID" --attempt "$attempt")
    BASE_URL=http://127.0.0.1:$PORT
    PORT_LOCK_FILE=$PORT_LOCK_ROOT/$PORT.lock
    exec {candidate_lock_fd}> "$PORT_LOCK_FILE"
    if ! /usr/bin/flock --exclusive --nonblock "$candidate_lock_fd"; then
        exec {candidate_lock_fd}>&-
        PORT_LOCK_FILE=
        "$CMPILOT_PY" "$PORT_HELPER" record-attempt \
            --record "$ARTIFACT_DIR/server-port-attempts.jsonl" \
            --job-id "$SLURM_JOB_ID" --attempt "$attempt" --port "$PORT" \
            --outcome ACTIVE_ENDPOINT_CLAIM_RETRY \
            >> "$ARTIFACT_DIR/server-port-helper.stdout"
        continue
    fi
    PORT_LOCK_FD=$candidate_lock_fd
    printf '%q ' "$VLLM_PY" -m vllm.entrypoints.openai.api_server \
        --host 127.0.0.1 --port "$PORT" --model "$MODEL" --tokenizer "$MODEL" \
        --served-model-name "$MODEL_ID" --dtype bfloat16 --tensor-parallel-size 2 \
        --max-model-len 32768 --max-num-seqs 1 --gpu-memory-utilization 0.90 \
        --seed "$TASK_SEED" --enforce-eager --reasoning-parser qwen3 \
        --language-model-only --generation-config vllm \
        > "$ARTIFACT_DIR/server-command.txt"
    printf '\n' >> "$ARTIFACT_DIR/server-command.txt"

    : > "$ARTIFACT_DIR/server.stdout"
    : > "$ARTIFACT_DIR/server.stderr"
    setsid "$VLLM_PY" -m vllm.entrypoints.openai.api_server \
        --host 127.0.0.1 \
        --port "$PORT" \
        --model "$MODEL" \
        --tokenizer "$MODEL" \
        --served-model-name "$MODEL_ID" \
        --dtype bfloat16 \
        --tensor-parallel-size 2 \
        --max-model-len 32768 \
        --max-num-seqs 1 \
        --gpu-memory-utilization 0.90 \
        --seed "$TASK_SEED" \
        --enforce-eager \
        --reasoning-parser qwen3 \
        --language-model-only \
        --generation-config vllm \
        > "$ARTIFACT_DIR/server.stdout" \
        2> "$ARTIFACT_DIR/server.stderr" &
    SERVER_PID=$!
    printf '%s\n' "$SERVER_PID" > "$ARTIFACT_DIR/server.pid"

    ready=0
    bind_collision=0
    for _ in $(seq 1 360); do
        if ! kill -0 "$SERVER_PID" 2>/dev/null; then
            set +e
            wait "$SERVER_PID"
            server_status=$?
            set -e
            SERVER_PID=
            if "$CMPILOT_PY" "$PORT_HELPER" classify-bind-failure \
                --stderr "$ARTIFACT_DIR/server.stderr" \
                --exit-code "$server_status" \
                --record "$ARTIFACT_DIR/server-bind-classification-$attempt.json" \
                >> "$ARTIFACT_DIR/server-port-helper.stdout"; then
                cp "$ARTIFACT_DIR/server-command.txt" \
                    "$ARTIFACT_DIR/server-bind-attempt-$attempt.command.txt"
                cp "$ARTIFACT_DIR/server.stdout" \
                    "$ARTIFACT_DIR/server-bind-attempt-$attempt.stdout"
                cp "$ARTIFACT_DIR/server.stderr" \
                    "$ARTIFACT_DIR/server-bind-attempt-$attempt.stderr"
                "$CMPILOT_PY" "$PORT_HELPER" record-attempt \
                    --record "$ARTIFACT_DIR/server-port-attempts.jsonl" \
                    --job-id "$SLURM_JOB_ID" --attempt "$attempt" --port "$PORT" \
                    --outcome EADDRINUSE_RETRY --server-exit-code "$server_status" \
                    >> "$ARTIFACT_DIR/server-port-helper.stdout"
                release_port_claim
                bind_collision=1
                break
            fi
            "$CMPILOT_PY" "$PORT_HELPER" record-attempt \
                --record "$ARTIFACT_DIR/server-port-attempts.jsonl" \
                --job-id "$SLURM_JOB_ID" --attempt "$attempt" --port "$PORT" \
                --outcome FATAL_SERVER_EXIT --server-exit-code "$server_status" \
                >> "$ARTIFACT_DIR/server-port-helper.stdout"
            if [ "$server_status" -eq 0 ]; then server_status=1; fi
            exit "$server_status"
        fi
        status=$(/usr/bin/curl --noproxy '*' --silent \
            --output "$ARTIFACT_DIR/health-response.raw" \
            --write-out '%{http_code}' "$BASE_URL/health" || true)
        if [ "$status" = 200 ]; then
            ready=1
            server_selected=1
            printf '%s\n' "$PORT" > "$ARTIFACT_DIR/selected-server-port.txt"
            printf '%s\n' "$BASE_URL" > "$ARTIFACT_DIR/server-base-url.txt"
            "$CMPILOT_PY" "$PORT_HELPER" record-attempt \
                --record "$ARTIFACT_DIR/server-port-attempts.jsonl" \
                --job-id "$SLURM_JOB_ID" --attempt "$attempt" --port "$PORT" \
                --outcome SERVER_READY \
                >> "$ARTIFACT_DIR/server-port-helper.stdout"
            break
        fi
        sleep 1
    done
    if [ "$server_selected" -eq 1 ]; then break; fi
    if [ "$bind_collision" -eq 1 ]; then continue; fi
    "$CMPILOT_PY" "$PORT_HELPER" record-attempt \
        --record "$ARTIFACT_DIR/server-port-attempts.jsonl" \
        --job-id "$SLURM_JOB_ID" --attempt "$attempt" --port "$PORT" \
        --outcome HEALTH_TIMEOUT \
        >> "$ARTIFACT_DIR/server-port-helper.stdout"
    exit 1
done
printf '%s\n' "$server_selected" > "$ARTIFACT_DIR/server-ready.txt"
test "$server_selected" -eq 1
/usr/bin/curl --noproxy '*' --silent --show-error "$BASE_URL/v1/models" \
    > "$ARTIFACT_DIR/models-response.json"

set +e
"$CMPILOT_PY" "$PROJECT/scripts/run_qualification_task.py" \
    --project-root "$PROJECT" \
    --suite-manifest "$SUITE" \
    --suite-reference "$SUITE_REFERENCE" \
    --task-manifest "$TASK" \
    --freeze-manifest "$FREEZE" \
    --artifact-directory "$RUN_ARTIFACT" \
    --base-url "$BASE_URL/v1" \
    --model "$MODEL_ID" \
    --tokenizer-path "$MODEL" \
    --mini-python "$MINI_PY" \
    --agent-config-source "$AGENT_CONFIG_SOURCE" \
    --infrastructure-amendment "$INFRASTRUCTURE_AMENDMENT" \
    --seed "$TASK_SEED" \
    --agent-timeout 600 \
    --server-pid "$SERVER_PID" \
    --runtime-integrity "$ARTIFACT_DIR/environment-verification/result.json" \
    > "$ARTIFACT_DIR/qualification-runner.stdout" \
    2> "$ARTIFACT_DIR/qualification-runner.stderr"
runner_status=$?
set -e
printf '%s\n' "$runner_status" > "$ARTIFACT_DIR/qualification-runner.exit"
set +e
cleanup_server
server_shutdown_status=$?
set -e
if [ "$runner_status" -ne 0 ]; then exit "$runner_status"; fi
if [ "$server_shutdown_status" -ne 0 ]; then exit 2; fi
exit 0
'''


def render(
    task_id: str,
    seed: int,
    freeze_sha256: str | None = None,
    *,
    submission_gate: dict[str, object] | None = None,
    technical_rerun: bool = False,
) -> str:
    gate = submission_gate or validate_submission_gate(ROOT)
    if freeze_sha256 is not None and freeze_sha256 != gate["scientific_freeze_sha256"]:
        raise RuntimeError("render freeze differs from canonical submission gate")
    if gate["seeds"].get(task_id) != seed:
        raise RuntimeError("render seed differs from canonical submission gate")
    role = "primary" if task_id in PRIMARY_TASKS else "reserve"
    job_name = "qwen36-" + task_id.replace("qnm-", "")
    rerun_metadata = ""
    rerun_artifacts = ""
    if technical_rerun:
        if task_id != TECHNICAL_RERUN_TASK:
            raise ValueError("the frozen technical rerun is only valid for qnm-p01")
        job_name += "-tr26036r1"
        rerun_metadata = "\n".join(
            (
                f"TECHNICAL_RERUN_OF={TECHNICAL_RERUN_OF}",
                f"TECHNICAL_RERUN_NUMBER={TECHNICAL_RERUN_NUMBER}",
                f"TECHNICAL_ROOT_QUALIFICATION={TECHNICAL_ROOT_QUALIFICATION}",
                f"QUALIFICATION_TASK_ID={task_id}",
                f"QUALIFICATION_SEED={seed}",
            )
        )
        rerun_artifacts = "\n".join(
            (
                "printf '%s\\n' \"$TECHNICAL_RERUN_OF\" > "
                '"$ARTIFACT_DIR/technical-rerun-of.txt"',
                "printf '%s\\n' \"$TECHNICAL_RERUN_NUMBER\" > "
                '"$ARTIFACT_DIR/technical-rerun-number.txt"',
                "printf '%s\\n' \"$TECHNICAL_ROOT_QUALIFICATION\" > "
                '"$ARTIFACT_DIR/technical-root-qualification.txt"',
                "printf '%s\\n' \"$QUALIFICATION_TASK_ID\" > "
                '"$ARTIFACT_DIR/qualification-task-id.txt"',
                "printf '%s\\n' \"$QUALIFICATION_SEED\" > "
                '"$ARTIFACT_DIR/qualification-seed.txt"',
            )
        )
    record_relative = gate["record_path"].relative_to(ROOT)
    amendment_relative = gate["infrastructure_amendment_path"].relative_to(ROOT)
    values = {
        "@@AMENDMENT_PATH@@": amendment_relative.as_posix(),
        "@@AMENDMENT_SHA256@@": gate["infrastructure_amendment_sha256"],
        "@@CPU_GATE@@": str(gate["cpu_gate_result_path"]),
        "@@CPU_GATE_SHA256@@": gate["cpu_gate_result_sha256"],
        "@@FREEZE_SHA256@@": gate["scientific_freeze_sha256"],
        "@@JOB_NAME@@": job_name,
        "@@TASK_ID@@": task_id,
        "@@TASK_ROLE@@": role,
        "@@TASK_SEED@@": str(seed),
        "@@SEED_SCHEDULE_SHA256@@": gate["seed_schedule_sha256"],
        "@@SUBMISSION_GATE_PATH@@": record_relative.as_posix(),
        "@@SUBMISSION_GATE_SHA256@@": gate["record_sha256"],
        "@@SUITE_REFERENCE_SHA256@@": gate["suite_reference_sha256"],
        "@@TECHNICAL_RERUN_ARTIFACTS@@": rerun_artifacts,
        "@@TECHNICAL_RERUN_METADATA@@": rerun_metadata,
    }
    value = TEMPLATE
    for marker, replacement in values.items():
        value = value.replace(marker, replacement)
    if "@@" in value or "{{" in value or "TODO" in value:
        raise RuntimeError(f"unresolved batch marker for {task_id}")
    equivalence = batch_gate_equivalence(
        value,
        gate=gate,
        task_id=task_id,
        seed=seed,
    )
    if not all(equivalence.values()):
        raise RuntimeError(f"generated batch gate mismatch: {equivalence}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-sha256", required=True)
    parser.add_argument(
        "--update",
        action="store_true",
        help="replace only the known generated qualification batch outputs",
    )
    arguments = parser.parse_args()
    gate = validate_submission_gate(ROOT)
    if gate["scientific_freeze_sha256"] != arguments.freeze_sha256:
        raise RuntimeError("provided freeze digest differs from final manifest")
    schedule = validate_seed_schedule(ROOT / SEED_SCHEDULE)["seeds"]
    rendered = [
        (
            task_id,
            output,
            render(
                task_id,
                schedule[task_id],
                arguments.freeze_sha256,
                submission_gate=gate,
            ),
        )
        for task_id, output in OUTPUTS.items()
    ]
    rendered.append(
        (
            TECHNICAL_RERUN_TASK,
            TECHNICAL_RERUN_OUTPUT,
            render(
                TECHNICAL_RERUN_TASK,
                schedule[TECHNICAL_RERUN_TASK],
                arguments.freeze_sha256,
                submission_gate=gate,
                technical_rerun=True,
            ),
        )
    )
    for task_id, output, content in rendered:
        if output.exists() and output.read_text(encoding="utf-8") != content:
            if not arguments.update:
                raise FileExistsError(f"refusing to overwrite different batch: {output}")
        output.write_text(content, encoding="utf-8", newline="\n")
        output.chmod(0o755)
        print(f"{task_id} {output} {sha256_file(output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
