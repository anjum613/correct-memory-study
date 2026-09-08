"""Bounded, job-owned runtime paths for qualification-side Unix IPC."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import stat
from typing import Any, Iterable, Mapping


RUNTIME_PATH_SCHEMA = "qwen32b-qualification-runtime-path-v1"
RUNTIME_OWNER_SCHEMA = "qwen32b-qualification-runtime-owner-v1"
RUNTIME_ROOT = Path("/tmp")
RUNTIME_PREFIX = "cmq-"
MAX_SLURM_JOB_ID_DIGITS = 20
ZMQ_UUID_TOKEN = "00000000-0000-0000-0000-000000000000"
ZMQ_UNIX_PATH_HARD_LIMIT_BYTES = 107
ZMQ_UNIX_PATH_SAFE_MAX_BYTES = 90
_JOB_ID = re.compile(rf"[0-9]{{1,{MAX_SLURM_JOB_ID_DIGITS}}}")
_OWNER_FILE = ".cmpilot-runtime-owner.json"


class QualificationRuntimePathError(RuntimeError):
    """A qualification runtime path violates its safety contract."""


def normalize_job_id(job_id: str | int) -> str:
    value = str(job_id)
    if _JOB_ID.fullmatch(value) is None:
        raise QualificationRuntimePathError(
            "Slurm job ID must contain 1 to "
            f"{MAX_SLURM_JOB_ID_DIGITS} decimal digits: {value!r}"
        )
    return value


def runtime_directory(
    job_id: str | int, *, runtime_root: Path = RUNTIME_ROOT
) -> Path:
    """Return the task-independent, bounded runtime directory for a job."""
    return runtime_root / f"{RUNTIME_PREFIX}{normalize_job_id(job_id)}"


def zmq_socket_path(
    job_id: str | int,
    *,
    runtime_root: Path = RUNTIME_ROOT,
    token: str = ZMQ_UUID_TOKEN,
) -> Path:
    """Model vLLM's ``VLLM_RPC_BASE_PATH/<uuid4>`` filesystem path."""
    if len(token.encode("ascii")) != len(ZMQ_UUID_TOKEN):
        raise QualificationRuntimePathError("unexpected vLLM ZeroMQ token length")
    return runtime_directory(job_id, runtime_root=runtime_root) / token


def path_bytes(path: Path) -> int:
    return len(os.fsencode(path))


def runtime_path_record(
    *,
    job_id: str | int,
    task_id: str,
    persistent_artifact_root: Path,
    runtime_root: Path = RUNTIME_ROOT,
) -> dict[str, Any]:
    """Describe persistent and ephemeral paths without budgeting the former."""
    normalized = normalize_job_id(job_id)
    runtime = runtime_directory(normalized, runtime_root=runtime_root)
    socket = zmq_socket_path(normalized, runtime_root=runtime_root)
    socket_bytes = path_bytes(socket)
    address = "ipc://" + os.fspath(socket)
    persistent = persistent_artifact_root / normalized
    return {
        "hard_limit_bytes": ZMQ_UNIX_PATH_HARD_LIMIT_BYTES,
        "ipc_address": address,
        "ipc_address_bytes": len(os.fsencode(address)),
        "job_id": normalized,
        "pass": socket_bytes <= ZMQ_UNIX_PATH_SAFE_MAX_BYTES,
        "persistent_artifact_directory": os.fspath(persistent),
        "persistent_artifact_path_budget_applies": False,
        "runtime_directory": os.fspath(runtime),
        "runtime_directory_bytes": path_bytes(runtime),
        "runtime_path_contains_task_id": task_id in os.fspath(runtime),
        "safe_maximum_bytes": ZMQ_UNIX_PATH_SAFE_MAX_BYTES,
        "safety_margin_below_hard_limit_bytes": (
            ZMQ_UNIX_PATH_HARD_LIMIT_BYTES - ZMQ_UNIX_PATH_SAFE_MAX_BYTES
        ),
        "schema": RUNTIME_PATH_SCHEMA,
        "task_id": task_id,
        "zmq_socket_path": os.fspath(socket),
        "zmq_socket_path_bytes": socket_bytes,
    }


def legacy_runtime_socket_path(
    *, persistent_artifact_root: Path, job_id: str | int
) -> Path:
    """Model job 25908's rejected artifact-nested runtime path."""
    return (
        persistent_artifact_root
        / normalize_job_id(job_id)
        / "runtime-scratch"
        / ZMQ_UUID_TOKEN
    )


def suite_runtime_path_record(
    tasks: Iterable[Mapping[str, Any]],
    *,
    job_ids: Iterable[str | int],
    runtime_root: Path = RUNTIME_ROOT,
) -> dict[str, Any]:
    job_id_values = tuple(job_ids)
    rows = []
    legacy_rows = []
    for task in tasks:
        task_id = str(task["task_id"])
        artifact_root = Path(str(task["artifact_destination"]))
        for job_id in job_id_values:
            row = runtime_path_record(
                job_id=job_id,
                task_id=task_id,
                persistent_artifact_root=artifact_root,
                runtime_root=runtime_root,
            )
            rows.append(row)
            legacy = legacy_runtime_socket_path(
                persistent_artifact_root=artifact_root,
                job_id=job_id,
            )
            legacy_rows.append(
                {
                    "job_id": normalize_job_id(job_id),
                    "legacy_path": os.fspath(legacy),
                    "legacy_path_bytes": path_bytes(legacy),
                    "passes_safe_maximum": (
                        path_bytes(legacy) <= ZMQ_UNIX_PATH_SAFE_MAX_BYTES
                    ),
                    "task_id": task_id,
                }
            )
    maximum = max((row["zmq_socket_path_bytes"] for row in rows), default=0)
    return {
        "hard_limit_bytes": ZMQ_UNIX_PATH_HARD_LIMIT_BYTES,
        "job_ids": [normalize_job_id(value) for value in job_id_values],
        "legacy_paths": legacy_rows,
        "maximum_zmq_socket_path_bytes": maximum,
        "pass": bool(rows)
        and all(row["pass"] for row in rows)
        and all(not row["runtime_path_contains_task_id"] for row in rows),
        "paths": rows,
        "runtime_root": os.fspath(runtime_root),
        "safe_maximum_bytes": ZMQ_UNIX_PATH_SAFE_MAX_BYTES,
        "schema": "qwen32b-qualification-runtime-path-suite-v1",
    }


def _owner_payload(job_id: str) -> bytes:
    return (
        json.dumps(
            {"job_id": job_id, "schema": RUNTIME_OWNER_SCHEMA},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _require_expected_path(
    path: Path, *, job_id: str | int, runtime_root: Path
) -> tuple[Path, str]:
    normalized = normalize_job_id(job_id)
    expected = runtime_directory(normalized, runtime_root=runtime_root)
    if path != expected:
        raise QualificationRuntimePathError(
            f"runtime path is not the exact job-owned target: {path} != {expected}"
        )
    return expected, normalized


def prepare_runtime_directory(
    path: Path, *, job_id: str | int, runtime_root: Path = RUNTIME_ROOT
) -> dict[str, Any]:
    expected, normalized = _require_expected_path(
        path, job_id=job_id, runtime_root=runtime_root
    )
    if expected.exists() or expected.is_symlink():
        raise FileExistsError(f"runtime path already exists: {expected}")
    expected.mkdir(mode=0o700)
    expected.chmod(0o700)
    owner = expected / _OWNER_FILE
    owner.write_bytes(_owner_payload(normalized))
    owner.chmod(0o600)
    information = expected.stat()
    passed = (
        information.st_uid == os.geteuid()
        and stat.S_IMODE(information.st_mode) == 0o700
    )
    if not passed:
        raise QualificationRuntimePathError("runtime directory ownership or mode is unsafe")
    return {
        "job_id": normalized,
        "mode": "0700",
        "owner_marker": os.fspath(owner),
        "pass": True,
        "runtime_directory": os.fspath(expected),
        "schema": "qwen32b-qualification-runtime-preparation-v1",
    }


def cleanup_runtime_directory(
    path: Path, *, job_id: str | int, runtime_root: Path = RUNTIME_ROOT
) -> dict[str, Any]:
    expected, normalized = _require_expected_path(
        path, job_id=job_id, runtime_root=runtime_root
    )
    if not expected.exists() and not expected.is_symlink():
        return {
            "already_absent": True,
            "job_id": normalized,
            "pass": True,
            "runtime_directory": os.fspath(expected),
            "schema": "qwen32b-qualification-runtime-cleanup-v1",
        }
    if expected.is_symlink() or not expected.is_dir():
        raise QualificationRuntimePathError("runtime cleanup target is not a real directory")
    information = expected.stat()
    if information.st_uid != os.geteuid():
        raise QualificationRuntimePathError("runtime cleanup target has a different owner")
    owner = expected / _OWNER_FILE
    if not owner.is_file() or owner.is_symlink():
        raise QualificationRuntimePathError("runtime ownership marker is missing or unsafe")
    if owner.read_bytes() != _owner_payload(normalized):
        raise QualificationRuntimePathError("runtime ownership marker does not match the job")
    symlinks = [
        item.relative_to(expected).as_posix()
        for item in expected.rglob("*")
        if item.is_symlink()
    ]
    if symlinks:
        raise QualificationRuntimePathError(
            f"runtime directory contains symlinks: {symlinks}"
        )
    shutil.rmtree(expected)
    return {
        "already_absent": False,
        "job_id": normalized,
        "pass": not expected.exists(),
        "runtime_directory": os.fspath(expected),
        "runtime_exists_after": expected.exists(),
        "schema": "qwen32b-qualification-runtime-cleanup-v1",
        "symlinks": symlinks,
    }
