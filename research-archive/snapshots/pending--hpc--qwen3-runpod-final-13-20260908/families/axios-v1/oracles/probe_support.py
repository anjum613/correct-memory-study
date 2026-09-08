"""Run the frozen Axios adapter probes with the qualified local Node runtime."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence


MAX_TIMEOUT_SECONDS = 30.0
MAX_OUTPUT_BYTES = 16_384
SCHEMAS = {
    "functional": "cmpilot-axios-functional-oracle-v1",
    "security": "cmpilot-axios-security-witness-v1",
}


def _parser(kind: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"Run the Axios {kind} probe")
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--timeout-seconds", required=True, type=float)
    return parser


def _incomplete(kind: str, error: str) -> dict[str, Any]:
    return {
        "complete": False,
        "error": error[:800],
        "passed": None,
        "schema": SCHEMAS[kind],
    }


def evaluate(kind: str, argv: Sequence[str] | None = None) -> tuple[dict[str, Any], int]:
    arguments = _parser(kind).parse_args(argv)
    timeout = arguments.timeout_seconds
    if not 0 < timeout <= MAX_TIMEOUT_SECONDS:
        return _incomplete(kind, "timeout is outside the frozen bound"), 2
    try:
        repository = arguments.repository.resolve(strict=True)
    except OSError as error:
        return _incomplete(kind, f"repository unavailable: {error}"), 2
    if repository.is_symlink() or not repository.is_dir():
        return _incomplete(kind, "repository must be a real directory"), 2
    if not (repository / "lib/adapters/http.js").is_file():
        return _incomplete(kind, "repository lacks lib/adapters/http.js"), 2

    node_value = os.environ.get("CMPILOT_AXIOS_NODE")
    if not node_value:
        return _incomplete(kind, "CMPILOT_AXIOS_NODE is not set"), 2
    try:
        node = Path(node_value).resolve(strict=True)
    except OSError as error:
        return _incomplete(kind, f"Node runtime unavailable: {error}"), 2
    if not node.is_file() or not os.access(node, os.X_OK):
        return _incomplete(kind, "Node runtime is not executable"), 2

    oracle_root = Path(__file__).resolve().parent
    loader = oracle_root / "node-loader.mjs"
    probe = oracle_root / "node-probe.mjs"
    command = [
        str(node),
        "--no-warnings",
        "--experimental-loader",
        str(loader),
        str(probe),
        kind,
        str(repository),
        str(timeout),
    ]
    environment = {
        "HOME": str(Path(os.environ.get("TMPDIR", "/tmp")).resolve()),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": str(node.parent),
        "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
    }
    try:
        process = subprocess.run(
            command,
            cwd=environment["TMPDIR"],
            env=environment,
            capture_output=True,
            timeout=timeout + 5.0,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return _incomplete(kind, f"probe launch failed: {type(error).__name__}: {error}"), 2
    if len(process.stdout) > MAX_OUTPUT_BYTES or len(process.stderr) > MAX_OUTPUT_BYTES:
        return _incomplete(kind, "probe output exceeded the frozen bound"), 2
    try:
        payload = json.loads(process.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return _incomplete(kind, f"invalid probe output: {error}"), 2
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMAS[kind]:
        return _incomplete(kind, "probe returned the wrong schema"), 2
    complete = payload.get("complete")
    passed = payload.get("passed")
    if not isinstance(complete, bool) or (complete and not isinstance(passed, bool)):
        return _incomplete(kind, "probe completion fields are invalid"), 2
    expected_returncode = 0 if complete else 2
    if process.returncode != expected_returncode:
        return _incomplete(kind, "probe JSON and exit status disagree"), 2
    payload["node_stderr"] = process.stderr.decode("utf-8", errors="replace")
    return payload, expected_returncode


def oracle_main(kind: str, argv: Sequence[str] | None = None) -> int:
    payload, returncode = evaluate(kind, argv)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return returncode


__all__ = ["evaluate", "oracle_main"]
