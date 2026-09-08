#!/usr/bin/env python3
"""Bounded, evidence-preserving lifecycle operations for Qwen3.6 vLLM jobs."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import signal
import time
from typing import Any


SCHEMA = "qwen36-server-shutdown-v1"
STATUS_SCHEMA = "qwen36-qualification-exit-status-v1"
DEFAULT_TERM_TIMEOUT_SECONDS = 30.0
DEFAULT_KILL_TIMEOUT_SECONDS = 10.0
DEFAULT_POLL_INTERVAL_SECONDS = 0.1


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _process_state(pid: int) -> str | None:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text(encoding="ascii").split()
    except FileNotFoundError:
        return None
    except OSError:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return None
        return "UNKNOWN"
    return fields[2] if len(fields) >= 3 else "UNKNOWN"


def process_running(pid: int) -> bool:
    """Treat a zombie as stopped; its owning shell can reap it without blocking."""
    state = _process_state(pid)
    return state is not None and state != "Z"


def _wait_stopped(pid: int, timeout: float, poll_interval: float) -> bool:
    deadline = time.monotonic() + timeout
    while process_running(pid) and time.monotonic() < deadline:
        time.sleep(poll_interval)
    return not process_running(pid)


def shutdown_process_group(
    pid: int,
    *,
    record: Path,
    term_timeout_seconds: float = DEFAULT_TERM_TIMEOUT_SECONDS,
    kill_timeout_seconds: float = DEFAULT_KILL_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> dict[str, Any]:
    """Stop one job-owned process group without any unbounded wait."""
    if pid <= 1:
        raise ValueError("refusing to signal an invalid server process group")
    if term_timeout_seconds < 0 or kill_timeout_seconds < 0:
        raise ValueError("shutdown timeouts must be non-negative")
    if poll_interval_seconds <= 0:
        raise ValueError("shutdown poll interval must be positive")

    started = time.monotonic()
    result: dict[str, Any] = {
        "force_kill_used": False,
        "graceful": True,
        "kill_timeout_seconds": kill_timeout_seconds,
        "pid": pid,
        "poll_interval_seconds": poll_interval_seconds,
        "schema": SCHEMA,
        "term_timeout_seconds": term_timeout_seconds,
    }
    if not process_running(pid):
        result.update(
            {
                "already_exited": True,
                "pass": True,
                "process_running_after": False,
                "shutdown_wall_time_seconds": time.monotonic() - started,
                "signals_sent": [],
            }
        )
        _write_json(record, result)
        return result

    process_group = os.getpgid(pid)
    if process_group != pid:
        raise ValueError(
            f"server PID {pid} is not its process-group leader (pgid={process_group})"
        )
    signals_sent: list[str] = []
    try:
        os.killpg(process_group, signal.SIGTERM)
        signals_sent.append("SIGTERM")
    except ProcessLookupError:
        pass
    stopped = _wait_stopped(pid, term_timeout_seconds, poll_interval_seconds)
    if not stopped:
        result["graceful"] = False
        result["force_kill_used"] = True
        try:
            os.killpg(process_group, signal.SIGKILL)
            signals_sent.append("SIGKILL")
        except ProcessLookupError:
            pass
        stopped = _wait_stopped(pid, kill_timeout_seconds, poll_interval_seconds)

    result.update(
        {
            "already_exited": False,
            "pass": stopped,
            "process_group": process_group,
            "process_running_after": not stopped,
            "shutdown_wall_time_seconds": time.monotonic() - started,
            "signals_sent": signals_sent,
        }
    )
    _write_json(record, result)
    return result


def _read_optional_exit(path: Path) -> int | None:
    if not path.is_file():
        return None
    return int(path.read_text(encoding="ascii").strip())


def record_exit_status(
    *,
    runner_exit_file: Path,
    server_shutdown_exit: int,
    port_release_exit: int,
    scratch_cleanup_exit: int,
    gpu_final_exit: int,
    manifest_exit: int,
    batch_exit: int,
    record: Path,
) -> dict[str, Any]:
    """Keep scientific runner, cleanup, manifest, and batch exits dimensional."""
    runner_exit = _read_optional_exit(runner_exit_file)
    stage_exits = {
        "artifact_manifest": manifest_exit,
        "gpu_final_capture": gpu_final_exit,
        "port_claim_release": port_release_exit,
        "runtime_scratch_cleanup": scratch_cleanup_exit,
        "server_shutdown": server_shutdown_exit,
    }
    outer_complete = all(value >= 0 for value in stage_exits.values())
    outer_pass = outer_complete and all(value == 0 for value in stage_exits.values())
    result = {
        "batch_exit_code": batch_exit,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "outer_finalizer_complete": outer_complete,
        "outer_finalizer_pass": outer_pass,
        "outer_finalizer_stage_exit_codes": stage_exits,
        "qualification_runner_exit_code": runner_exit,
        "runner_success": runner_exit == 0 if runner_exit is not None else None,
        "schema": STATUS_SCHEMA,
        "slurm_accounting": "recorded externally after job completion",
    }
    _write_json(record, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    shutdown = subparsers.add_parser("shutdown")
    shutdown.add_argument("--pid", required=True, type=int)
    shutdown.add_argument("--record", required=True, type=Path)
    shutdown.add_argument(
        "--term-timeout-seconds",
        type=float,
        default=DEFAULT_TERM_TIMEOUT_SECONDS,
    )
    shutdown.add_argument(
        "--kill-timeout-seconds",
        type=float,
        default=DEFAULT_KILL_TIMEOUT_SECONDS,
    )
    shutdown.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
    )
    status = subparsers.add_parser("record-status")
    status.add_argument("--runner-exit-file", required=True, type=Path)
    status.add_argument("--server-shutdown-exit", required=True, type=int)
    status.add_argument("--port-release-exit", required=True, type=int)
    status.add_argument("--scratch-cleanup-exit", required=True, type=int)
    status.add_argument("--gpu-final-exit", required=True, type=int)
    status.add_argument("--manifest-exit", required=True, type=int)
    status.add_argument("--batch-exit", required=True, type=int)
    status.add_argument("--record", required=True, type=Path)
    arguments = parser.parse_args()
    if arguments.command == "shutdown":
        result = shutdown_process_group(
            arguments.pid,
            record=arguments.record,
            term_timeout_seconds=arguments.term_timeout_seconds,
            kill_timeout_seconds=arguments.kill_timeout_seconds,
            poll_interval_seconds=arguments.poll_interval_seconds,
        )
    else:
        result = record_exit_status(
            runner_exit_file=arguments.runner_exit_file,
            server_shutdown_exit=arguments.server_shutdown_exit,
            port_release_exit=arguments.port_release_exit,
            scratch_cleanup_exit=arguments.scratch_cleanup_exit,
            gpu_final_exit=arguments.gpu_final_exit,
            manifest_exit=arguments.manifest_exit,
            batch_exit=arguments.batch_exit,
            record=arguments.record,
        )
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("pass", result.get("outer_finalizer_pass")) else 1


if __name__ == "__main__":
    raise SystemExit(main())
