#!/bin/bash
#SBATCH --job-name=mini-swe-multiturn-check
#SBATCH --partition=Virtual
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:05:00
#SBATCH --account=hpc
#SBATCH --qos=normal
#SBATCH --output=/home/s224049759/slurm-logs/mini-swe-multiturn-check-%j.out
#SBATCH --error=/home/s224049759/slurm-logs/mini-swe-multiturn-check-%j.err

set -euo pipefail

PROJECT=/home/s224049759/projects/correct-memory-study
CMPILOT_PY=/home/s224049759/environments/cmpilot-conda/bin/python
MINI_PY=/home/s224049759/environments/mini-swe-agent-smoke/bin/python
ARTIFACT_DIR=/home/s224049759/run-artifacts/mini-swe-multiturn-preflight/$SLURM_JOB_ID

test -x "$CMPILOT_PY"
test -x "$MINI_PY"
mkdir -p "$ARTIFACT_DIR"
hostname -f > "$ARTIFACT_DIR/hostname.txt"
git -C "$PROJECT" rev-parse HEAD > "$ARTIFACT_DIR/git-commit.txt"
env | LC_ALL=C sort > "$ARTIFACT_DIR/slurm-environment.txt"
module list > "$ARTIFACT_DIR/module-list.txt" 2>&1 || true
cp "$PROJECT/slurm/mini_swe_multiturn_preflight.sbatch" "$ARTIFACT_DIR/submitted-script.sbatch"
printf 'job_started_at=%s\n' "$(date --iso-8601=seconds)" > "$ARTIFACT_DIR/timestamps.txt"

record_installed_packages() {
    local python_executable=$1
    local destination=$2
    "$python_executable" - <<'PY' > "$destination"
from importlib.metadata import distributions

rows = []
for distribution in distributions():
    name = distribution.metadata.get("Name")
    if name:
        rows.append((name.lower(), f"{name}=={distribution.version}"))
for _, row in sorted(rows):
    print(row)
PY
}

record_installed_packages "$CMPILOT_PY" "$ARTIFACT_DIR/installed-packages-cmpilot.txt"
record_installed_packages "$MINI_PY" "$ARTIFACT_DIR/installed-packages-agent.txt"
"$CMPILOT_PY" --version > "$ARTIFACT_DIR/python-versions.txt" 2>&1
"$MINI_PY" --version >> "$ARTIFACT_DIR/python-versions.txt" 2>&1

set +e
(
    cd "$PROJECT"
    "$CMPILOT_PY" -m cmpilot multiturn-preflight \
        --mini-python "$MINI_PY" \
        --artifact-dir "$ARTIFACT_DIR" \
        --timeout 90
) > "$ARTIFACT_DIR/harness.stdout.log" 2> "$ARTIFACT_DIR/harness.stderr.log"
HARNESS_STATUS=$?
set -e
printf 'harness_exit_status=%s\n' "$HARNESS_STATUS" >> "$ARTIFACT_DIR/timestamps.txt"
if [ "$HARNESS_STATUS" -ne 0 ]; then
    printf 'job_finished_at=%s\n' "$(date --iso-8601=seconds)" >> "$ARTIFACT_DIR/timestamps.txt"
    exit "$HARNESS_STATUS"
fi

"$CMPILOT_PY" - "$ARTIFACT_DIR/result.json" <<'PY'
import json
import sys
from pathlib import Path

result = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if result.get("classification") != "MULTITURN_ADAPTER_PREFLIGHT_PASS":
    raise SystemExit("unexpected preflight classification")
checks = result.get("checks", {})
if not checks or not all(checks.values()):
    raise SystemExit("one or more preflight checks failed")
if result.get("mock_request_count") < 2:
    raise SystemExit("fewer than two model requests were accepted")
PY

printf 'batch_wrapper_complete=true\n' >> "$ARTIFACT_DIR/process-cleanup.txt"
printf 'job_finished_at=%s\n' "$(date --iso-8601=seconds)" >> "$ARTIFACT_DIR/timestamps.txt"
printf 'job_exit_status=0\n' >> "$ARTIFACT_DIR/timestamps.txt"
