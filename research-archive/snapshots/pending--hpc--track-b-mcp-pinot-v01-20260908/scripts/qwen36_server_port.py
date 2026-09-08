#!/usr/bin/env python3
"""Deterministic, bounded server-port infrastructure for Qwen3.6 jobs.

vLLM 0.19 rejects ``--port 0`` at its CLI boundary.  Qualification jobs
therefore derive a small schedule of job-local candidate ports and let vLLM
itself perform each bind.  The launcher may advance through this schedule only
after an exact pre-model ``EADDRINUSE`` traceback.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re


LOOPBACK_HOST = "127.0.0.1"
MIN_PORT = 20_000
PORT_COUNT = 40_000
MAX_BIND_ATTEMPTS = 4
JOB_MULTIPLIER = 15_485_863
ATTEMPT_STEP = 7_919
SELECTION_METHOD = "job-derived-vllm-owned-bind-v1"

_EADDRINUSE = re.compile(
    r"^(?:\(APIServer pid=\d+\) )?OSError: "
    r"\[Errno 98\] Address already in use$",
    re.MULTILINE,
)
_BIND_TRACE_MARKERS = (
    "create_server_socket",
    "sock.bind(addr)",
    "setup_server(args)",
)
_MODEL_LOAD_MARKERS = (
    "EngineCore",
    "Loading model weights",
    "Loading weights took",
    "Model loading took",
    "Starting to load model",
)


def _job_number(job_id: str | int) -> int:
    value = str(job_id)
    if not value.isascii() or not value.isdecimal() or int(value) <= 0:
        raise ValueError("Slurm job ID must be a positive ASCII decimal integer")
    return int(value)


def candidate_port(job_id: str | int, attempt: int) -> int:
    """Return the one-based attempt's deterministic candidate TCP port."""
    number = _job_number(job_id)
    if not 1 <= attempt <= MAX_BIND_ATTEMPTS:
        raise ValueError(f"attempt must be in 1..{MAX_BIND_ATTEMPTS}")
    offset = (number * JOB_MULTIPLIER + (attempt - 1) * ATTEMPT_STEP) % PORT_COUNT
    return MIN_PORT + offset


def candidate_schedule(job_id: str | int) -> tuple[int, ...]:
    return tuple(
        candidate_port(job_id, attempt)
        for attempt in range(1, MAX_BIND_ATTEMPTS + 1)
    )


def base_url(port: int) -> str:
    if not MIN_PORT <= port < MIN_PORT + PORT_COUNT:
        raise ValueError("port is outside the qualification allocation range")
    return f"http://{LOOPBACK_HOST}:{port}"


def is_explicit_pre_model_address_in_use(stderr: str, exit_code: int) -> bool:
    """Recognize only vLLM's exact pre-model bind-collision traceback."""
    return bool(
        exit_code != 0
        and _EADDRINUSE.search(stderr)
        and all(marker in stderr for marker in _BIND_TRACE_MARKERS)
        and not any(marker in stderr for marker in _MODEL_LOAD_MARKERS)
    )


def inspect_vllm_019_port_contract(api_server: Path, argparse_utils: Path) -> dict[str, object]:
    """Statically attest the locally installed vLLM 0.19 binding contract."""
    api_text = api_server.read_text(encoding="utf-8")
    parser_text = argparse_utils.read_text(encoding="utf-8")
    bind_index = api_text.find("sock = create_server_socket(sock_addr)")
    engine_index = api_text.find("async with build_async_engine_client(")
    result = {
        "api_server_path": str(api_server),
        "argparse_utils_path": str(argparse_utils),
        "bind_before_engine_setup": 0 <= bind_index < engine_index,
        "cli_accepts_kernel_assigned_port_zero": False,
        "cli_port_range": {"minimum": 1024, "maximum": 65535},
        "create_socket_binds_directly": "sock.bind(addr)" in api_text,
        "server_socket_is_retained": "return listen_address, sock" in api_text,
        "version": "0.19.0",
    }
    result["pass"] = bool(
        result["bind_before_engine_setup"]
        and result["create_socket_binds_directly"]
        and result["server_socket_is_retained"]
        and "1024 <= value <= 65535" in parser_text
    )
    return result


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _append_jsonl(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")


def schedule_record(job_id: str | int) -> dict[str, object]:
    number = _job_number(job_id)
    ports = candidate_schedule(number)
    return {
        "candidate_base_urls": [base_url(port) for port in ports],
        "candidate_ports": list(ports),
        "host": LOOPBACK_HOST,
        "job_id": str(number),
        "max_bind_attempts": MAX_BIND_ATTEMPTS,
        "port_range": {
            "count": PORT_COUNT,
            "maximum": MIN_PORT + PORT_COUNT - 1,
            "minimum": MIN_PORT,
        },
        "retry_condition": "exact pre-model EADDRINUSE only",
        "schema": "qwen36-server-port-schedule-v1",
        "selection_method": SELECTION_METHOD,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    schedule = subparsers.add_parser("schedule")
    schedule.add_argument("--job-id", required=True)
    schedule.add_argument("--record", type=Path, required=True)

    candidate = subparsers.add_parser("candidate")
    candidate.add_argument("--job-id", required=True)
    candidate.add_argument("--attempt", required=True, type=int)

    classify = subparsers.add_parser("classify-bind-failure")
    classify.add_argument("--stderr", type=Path, required=True)
    classify.add_argument("--exit-code", type=int, required=True)
    classify.add_argument("--record", type=Path, required=True)

    record = subparsers.add_parser("record-attempt")
    record.add_argument("--record", type=Path, required=True)
    record.add_argument("--job-id", required=True)
    record.add_argument("--attempt", required=True, type=int)
    record.add_argument("--port", required=True, type=int)
    record.add_argument(
        "--outcome",
        choices=(
            "ACTIVE_ENDPOINT_CLAIM_RETRY",
            "EADDRINUSE_RETRY",
            "FATAL_SERVER_EXIT",
            "HEALTH_TIMEOUT",
            "SERVER_READY",
        ),
        required=True,
    )
    record.add_argument("--server-exit-code", type=int)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    if arguments.command == "schedule":
        result = schedule_record(arguments.job_id)
        _write_json(arguments.record, result)
        print(json.dumps(result, sort_keys=True))
        return 0
    if arguments.command == "candidate":
        print(candidate_port(arguments.job_id, arguments.attempt))
        return 0
    if arguments.command == "classify-bind-failure":
        stderr = arguments.stderr.read_text(encoding="utf-8", errors="replace")
        matched = is_explicit_pre_model_address_in_use(stderr, arguments.exit_code)
        result = {
            "classification": (
                "PRE_MODEL_EADDRINUSE" if matched else "NOT_RETRYABLE_BIND_COLLISION"
            ),
            "exit_code": arguments.exit_code,
            "pass": matched,
            "schema": "qwen36-server-bind-failure-classification-v1",
            "stderr_sha256": hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
        }
        _write_json(arguments.record, result)
        print(json.dumps(result, sort_keys=True))
        return 0 if matched else 1
    if arguments.command == "record-attempt":
        expected = candidate_port(arguments.job_id, arguments.attempt)
        if arguments.port != expected:
            raise ValueError("recorded port differs from the deterministic schedule")
        record = {
            "attempt": arguments.attempt,
            "base_url": base_url(arguments.port),
            "job_id": str(_job_number(arguments.job_id)),
            "observed_at_utc": datetime.now(UTC).isoformat(),
            "outcome": arguments.outcome,
            "port": arguments.port,
            "schema": "qwen36-server-port-attempt-v1",
        }
        if arguments.server_exit_code is not None:
            record["server_exit_code"] = arguments.server_exit_code
        _append_jsonl(arguments.record, record)
        print(json.dumps(record, sort_keys=True))
        return 0
    raise AssertionError(f"unhandled command: {arguments.command}")


if __name__ == "__main__":
    raise SystemExit(main())
