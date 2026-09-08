#!/usr/bin/env python3
"""Restart an externally terminated tmux runner without bypassing its safeguards."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import shlex
import subprocess
import time
from datetime import datetime, timezone


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def append_event(path: Path, event: str, **details: object) -> None:
    payload = {"at": utc_now(), "event": event, **details}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_progress(path: Path) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


def session_exists(name: str) -> bool:
    return subprocess.run(
        ["tmux", "has-session", "-t", name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def runner_lock_is_free(path: Path) -> bool:
    path.touch(exist_ok=True)
    with path.open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(handle, fcntl.LOCK_UN)
    return True


def launch_runner(output_root: Path, runner: Path, session: str) -> subprocess.CompletedProcess[str]:
    log_path = output_root / "runner.log"
    command = (
        "exec /usr/bin/python3 "
        + shlex.quote(str(runner))
        + " run --output-root "
        + shlex.quote(str(output_root))
        + " >> "
        + shlex.quote(str(log_path))
        + " 2>&1"
    )
    return subprocess.run(
        ["tmux", "new-session", "-d", "-s", session, "-c", str(output_root), command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--poll-seconds", type=int, default=30)
    parser.add_argument("--missing-grace-seconds", type=int, default=30)
    parser.add_argument("--restart-window-seconds", type=int, default=3600)
    parser.add_argument("--max-restarts-in-window", type=int, default=3)
    args = parser.parse_args()

    output_root = args.output_root.resolve()
    runner = args.runner.resolve()
    event_log = output_root / "watchdog.log"
    watchdog_lock = output_root / "watchdog.lock"
    watchdog_lock.touch(exist_ok=True)
    lock_handle = watchdog_lock.open("a+")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        append_event(event_log, "duplicate_watchdog_refused")
        return 2

    if not runner.is_file():
        append_event(event_log, "invalid_runner", runner=str(runner))
        return 2

    append_event(
        event_log,
        "watchdog_started",
        pid=os.getpid(),
        runner=str(runner),
        session=args.session,
    )
    missing_since: float | None = None
    restart_times: list[float] = []

    while True:
        progress = read_progress(output_root / "progress.json")
        if progress is None:
            append_event(event_log, "progress_unreadable")
            time.sleep(args.poll_seconds)
            continue

        status = str(progress.get("status", ""))
        completed = progress.get("completed")
        if status in {"COMPLETED", "STOPPED_INFRASTRUCTURE"}:
            append_event(event_log, "watchdog_stopped", status=status, completed=completed)
            return 0
        if status != "RUNNING":
            append_event(event_log, "watchdog_stopped_unknown_status", status=status, completed=completed)
            return 2

        if session_exists(args.session):
            missing_since = None
            time.sleep(args.poll_seconds)
            continue

        if not runner_lock_is_free(output_root / "runner.lock"):
            missing_since = None
            append_event(event_log, "runner_alive_without_tmux", completed=completed)
            time.sleep(args.poll_seconds)
            continue

        monotonic_now = time.monotonic()
        if missing_since is None:
            missing_since = monotonic_now
            append_event(event_log, "missing_runner_observed", completed=completed)
            time.sleep(args.poll_seconds)
            continue
        if monotonic_now - missing_since < args.missing_grace_seconds:
            time.sleep(args.poll_seconds)
            continue

        restart_times = [
            stamp
            for stamp in restart_times
            if monotonic_now - stamp < args.restart_window_seconds
        ]
        if len(restart_times) >= args.max_restarts_in_window:
            append_event(
                event_log,
                "restart_rate_breaker",
                completed=completed,
                restarts_in_window=len(restart_times),
                window_seconds=args.restart_window_seconds,
            )
            return 3

        launched = launch_runner(output_root, runner, args.session)
        append_event(
            event_log,
            "runner_restart_attempt",
            completed=completed,
            returncode=launched.returncode,
            stderr=launched.stderr.strip(),
        )
        if launched.returncode == 0:
            restart_times.append(monotonic_now)
        missing_since = None
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
