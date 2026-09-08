set -euo pipefail
mapfile -t SERVER_CMD < <(
    /usr/bin/jq -r '.argv[]' \
        "$ARTIFACT_DIR/generated-load-gate-plan/server-command.json"
)
[[ "${SERVER_CMD[0]}" == "$PYTHON" ]]
[[ "${SERVER_CMD[*]}" == *"--guided-decoding-backend lm-format-enforcer"* ]]
[[ "${SERVER_CMD[*]}" != *"--guided-decoding-backend outlines"* ]]
SERVER_LAUNCH_CMD=("${SERVER_CMD[0]}" -X importtime "${SERVER_CMD[@]:1}")
