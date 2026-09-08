#!/usr/bin/env fish

set -l script_dir (path resolve (path dirname (status filename)))
set -l runner_root $script_dir
set -l canonical_codex /home/anjum/.local/npm/bin/codex
if set -q TRACK_A_RUNNER_ROOT
    set runner_root (path resolve $TRACK_A_RUNNER_ROOT)
end
if contains -- --codex-bin $argv
    echo "ERROR: --codex-bin is frozen by the Track A launcher: $canonical_codex" >&2
    exit 2
end
set -l runner_argv --codex-bin $canonical_codex $argv

# Read-only operational queries must remain available while the production
# runner owns the lock, and must not create the selected runner root.
if contains -- --status $argv; or contains -- --events $argv; or contains -- --doctor $argv
    env PYTHONDONTWRITEBYTECODE=1 python3 $script_dir/track_a_runner_v2.py --runner-root $runner_root $runner_argv
    exit $status
end

command mkdir -p $runner_root
if test $status -ne 0
    echo "ERROR: cannot create Track A runner root: $runner_root" >&2
    exit 1
end

set -l lock_path $runner_root/track-a-runner.lock

command flock --exclusive --nonblock --no-fork --conflict-exit-code 73 \
    $lock_path \
    env PYTHONDONTWRITEBYTECODE=1 python3 $script_dir/track_a_runner_v2.py --runner-root $runner_root $runner_argv
set -l runner_status $status

if test $runner_status -eq 73
    echo "ERROR: another Track A autonomous runner holds $lock_path; refusing to start" >&2
end

exit $runner_status
