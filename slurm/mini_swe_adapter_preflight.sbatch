#!/usr/bin/env bash
#SBATCH --job-name=mini-swe-adapter-check
#SBATCH --partition=Virtual
#SBATCH --account=hpc
#SBATCH --qos=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:05:00
#SBATCH --output=/home/s224049759/slurm-logs/mini-swe-adapter-preflight-%j.out
#SBATCH --error=/home/s224049759/slurm-logs/mini-swe-adapter-preflight-%j.err

set -euo pipefail

PROJECT=/home/s224049759/projects/correct-memory-study
CMPILOT_PY=/home/s224049759/environments/cmpilot-conda/bin/python
MINI_PY=/home/s224049759/environments/mini-swe-agent-smoke/bin/python
ARTIFACT_ROOT=/home/s224049759/run-artifacts/mini-swe-adapter-preflight
ARTIFACT_DIR="$ARTIFACT_ROOT/$SLURM_JOB_ID"
SOURCE_FAILURE=/home/s224049759/run-artifacts/mini-swe-smoke-3/24670/agent.stderr.log

mkdir -p "$ARTIFACT_ROOT"
mkdir "$ARTIFACT_DIR"
exec > >(tee "$ARTIFACT_DIR/preflight.stdout.log") \
    2> >(tee "$ARTIFACT_DIR/preflight.stderr.log" >&2)
printf 'job_started_at=%s\n' "$(date --iso-8601=seconds)" > "$ARTIFACT_DIR/timestamps.txt"

on_exit() {
    local status=$?
    local remaining=
    set +e
    remaining=$(ps -eo pid=,args= | awk -v marker="$ARTIFACT_DIR/mini_swe_adapter.py" 'index($0, marker) && $0 !~ /awk -v marker/ {print}')
    if [ -n "$remaining" ]; then
        printf 'surviving_processes:\n%s\n' "$remaining" > "$ARTIFACT_DIR/process-cleanup.txt"
        status=1
    else
        printf 'no_adapter_process_remains\n' > "$ARTIFACT_DIR/process-cleanup.txt"
    fi
    printf 'job_finished_at=%s\n' "$(date --iso-8601=seconds)" >> "$ARTIFACT_DIR/timestamps.txt"
    printf 'job_exit_status=%s\n' "$status" >> "$ARTIFACT_DIR/timestamps.txt"
    if [ "$status" -eq 0 ]; then
        printf 'classification=ADAPTER_PREFLIGHT_PASS\nexit_status=0\n' > "$ARTIFACT_DIR/batch-result.txt"
    else
        printf 'classification=ADAPTER_PREFLIGHT_FAIL\nexit_status=%s\n' "$status" > "$ARTIFACT_DIR/batch-result.txt"
    fi
    trap - EXIT
    exit "$status"
}
trap on_exit EXIT

test -x "$CMPILOT_PY"
test -x "$MINI_PY"
test -f "$SOURCE_FAILURE"

{
    printf 'CMPILOT_PY=%s\n' "$(readlink -f "$CMPILOT_PY")"
    printf 'MINI_PY=%s\n' "$(readlink -f "$MINI_PY")"
} > "$ARTIFACT_DIR/executable-paths.txt"
{
    printf 'cmpilot: '
    "$CMPILOT_PY" --version
    printf 'mini-swe-agent: '
    "$MINI_PY" --version
} > "$ARTIFACT_DIR/python-versions.txt" 2>&1

hostname -f > "$ARTIFACT_DIR/hostname.txt"
git -C "$PROJECT" rev-parse HEAD > "$ARTIFACT_DIR/git-commit.txt"
git -C "$PROJECT" branch --show-current > "$ARTIFACT_DIR/git-branch.txt"
git -C "$PROJECT" --no-pager status --short --branch > "$ARTIFACT_DIR/project-git-status.txt"
cp -- "$0" "$ARTIFACT_DIR/submitted-script.sbatch"
cp -- "$SOURCE_FAILURE" "$ARTIFACT_DIR/job-24670-agent.stderr.log"
env | grep '^SLURM_' | LC_ALL=C sort > "$ARTIFACT_DIR/slurm-environment.txt"
printf 'PATH=%s\n' "$PATH" > "$ARTIFACT_DIR/path.txt"
printf 'partition=Virtual\ngpu_requested=false\nserver_started=false\ndummy_base_url=http://127.0.0.1:9/v1\n' \
    > "$ARTIFACT_DIR/execution-scope.txt"

if type module >/dev/null 2>&1; then
    module list > "$ARTIFACT_DIR/module-list.txt" 2>&1
else
    printf 'module command unavailable; no modules are required\n' > "$ARTIFACT_DIR/module-list.txt"
fi

"$MINI_PY" - <<'PY' > "$ARTIFACT_DIR/mini-swe-config-inspection.txt"
from importlib.metadata import files, version
print("mini-swe-agent", version("mini-swe-agent"))
for item in files("mini-swe-agent") or []:
    text = str(item)
    if any(term in text.lower() for term in [
        "config", "schema", "yaml", "example", "default"
    ]):
        print(text)
PY

mkdir "$ARTIFACT_DIR/schema-home"
HOME="$ARTIFACT_DIR/schema-home" \
XDG_CONFIG_HOME="$ARTIFACT_DIR/schema-home/config" \
"$MINI_PY" - <<'PY' > "$ARTIFACT_DIR/mini-swe-schema.txt"
from minisweagent.agents.default import AgentConfig
from minisweagent.environments.local import LocalEnvironmentConfig
from minisweagent.models.litellm_textbased_model import LitellmTextbasedModelConfig
for config_class in (AgentConfig, LocalEnvironmentConfig, LitellmTextbasedModelConfig):
    print(config_class.__name__)
    print("fields:", ",".join(config_class.model_fields))
    print("extra:", config_class.model_config.get("extra"))
PY

"$MINI_PY" - <<'PY' | LC_ALL=C sort > "$ARTIFACT_DIR/pip-freeze-agent.txt"
from importlib.metadata import distributions

for distribution in distributions():
    if name := distribution.metadata.get("Name"):
        print(f"{name}=={distribution.version}")
PY
"$CMPILOT_PY" -m pip freeze | LC_ALL=C sort > "$ARTIFACT_DIR/pip-freeze-cmpilot.txt"

printf '%q ' "$CMPILOT_PY" -m cmpilot adapter-preflight \
    --mini-python "$MINI_PY" \
    --artifact-dir "$ARTIFACT_DIR" \
    --timeout 45 > "$ARTIFACT_DIR/preflight-command.txt"
printf '\n' >> "$ARTIFACT_DIR/preflight-command.txt"

"$CMPILOT_PY" -m cmpilot adapter-preflight \
    --mini-python "$MINI_PY" \
    --artifact-dir "$ARTIFACT_DIR" \
    --timeout 45

"$CMPILOT_PY" - "$ARTIFACT_DIR/result.json" <<'PY' > "$ARTIFACT_DIR/result-validation.txt"
import json
import sys
from pathlib import Path

result = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert result["classification"] == "ADAPTER_PREFLIGHT_PASS", result
assert all(result["checks"].values()), result["checks"]
assert result["trajectory_metrics"]["model_request_count"] == 1
assert result["trajectory_metrics"]["command_count"] == 0
assert result["expected_error_type"] in {"APIConnectionError", "InternalServerError"}
assert "Connection error" in result["expected_error_message"]
print("ADAPTER_PREFLIGHT_PASS")
print("all acceptance checks passed")
PY

printf 'CPU adapter preflight passed; no model server started and no GPU requested.\n'
