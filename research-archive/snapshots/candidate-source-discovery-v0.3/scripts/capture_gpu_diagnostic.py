#!/usr/bin/env python3
"""Run one GPU diagnostic with an explicit mandatory/informational policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shlex
import subprocess
from typing import Sequence


_NAME = re.compile(r"[a-z0-9][a-z0-9._-]*")


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _coerce_bytes(value: bytes | str | None) -> bytes:
    if value is None:
        return b""
    return value if isinstance(value, bytes) else value.encode("utf-8")


def run_diagnostic(
    *,
    artifact_directory: Path,
    name: str,
    policy: str,
    command: Sequence[str],
    timeout: int,
) -> dict[str, object]:
    """Run and preserve one command without conflating information with a gate."""
    if _NAME.fullmatch(name) is None:
        raise ValueError(f"invalid diagnostic name: {name!r}")
    if policy not in {"informational", "mandatory"}:
        raise ValueError(f"invalid diagnostic policy: {policy!r}")
    if not command or not command[0]:
        raise ValueError("diagnostic command is empty")
    artifact_directory = artifact_directory.resolve(strict=True)
    prefix = artifact_directory / name
    argv = list(command)
    error = None
    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            timeout=timeout,
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as exception:
        exit_code = 124
        stdout = _coerce_bytes(exception.stdout)
        stderr = _coerce_bytes(exception.stderr)
        error = f"TimeoutExpired: diagnostic exceeded {timeout} seconds"
    except OSError as exception:
        exit_code = 127
        stdout = b""
        stderr = f"{type(exception).__name__}: {exception}\n".encode("utf-8")
        error = f"{type(exception).__name__}: {exception}"

    prefix.with_suffix(".stdout").write_bytes(stdout)
    prefix.with_suffix(".stderr").write_bytes(stderr)
    prefix.with_suffix(".exit-code.txt").write_text(
        f"{exit_code}\n", encoding="ascii", newline="\n"
    )
    diagnostic_succeeded = exit_code == 0
    batch_gate_passed = diagnostic_succeeded or policy == "informational"
    result: dict[str, object] = {
        "argv": argv,
        "batch_gate_passed": batch_gate_passed,
        "command": shlex.join(argv),
        "diagnostic_succeeded": diagnostic_succeeded,
        "exit_code": exit_code,
        "name": name,
        "policy": policy,
        "schema": "qwen36-gpu-diagnostic-v1",
        "stderr_path": str(prefix.with_suffix(".stderr")),
        "stdout_path": str(prefix.with_suffix(".stdout")),
        "timeout_seconds": timeout,
    }
    if error is not None:
        result["error"] = error
    _write_json(prefix.with_suffix(".result.json"), result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-directory", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument(
        "--policy", choices=("informational", "mandatory"), required=True
    )
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    arguments = parser.parse_args()
    command = list(arguments.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if arguments.timeout < 1:
        parser.error("--timeout must be positive")
    result = run_diagnostic(
        artifact_directory=arguments.artifact_directory,
        name=arguments.name,
        policy=arguments.policy,
        command=command,
        timeout=arguments.timeout,
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["batch_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
