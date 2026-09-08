#!/usr/bin/env bash
set -euo pipefail

output_root=/home/s224049759/projects/final-experiment-runs/controlled-synthetic-final-13-codex-v3
runner="$output_root/runtime-amendments/002-interrupted-finalization/run_controlled_synthetic_final_13_codex.py"
watchdog="$output_root/runtime-amendments/003-runner-watchdog/watch_final_13_codex.py"
main_session=final-13-codex-v3
watchdog_session=final-13-codex-v3-watchdog
resume_epoch=1788649500

while (( $(date +%s) < resume_epoch )); do
    sleep 30
done

if ! tmux has-session -t "$watchdog_session" 2>/dev/null; then
    tmux new-session -d -s "$watchdog_session" -c "$output_root" \
        "sleep 60; exec /usr/bin/python3 $watchdog --output-root $output_root --runner $runner --session $main_session >> $output_root/watchdog-supervisor.log 2>&1"
fi

exec /usr/bin/python3 "$runner" run --output-root "$output_root" >> "$output_root/runner.log" 2>&1
