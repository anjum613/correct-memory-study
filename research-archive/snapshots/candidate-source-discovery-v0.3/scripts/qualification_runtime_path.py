#!/usr/bin/env python3
"""Validate, create, or clean a bounded qualification runtime directory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.qualification import write_canonical_json  # noqa: E402
from cmpilot.qualification_runtime_paths import (  # noqa: E402
    QualificationRuntimePathError,
    cleanup_runtime_directory,
    prepare_runtime_directory,
    runtime_path_record,
)


def _write(path: Path, value: dict[str, Any]) -> None:
    write_canonical_json(path, value)
    print(json.dumps(value, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--job-id", required=True)
    validate.add_argument("--task-id", required=True)
    validate.add_argument("--persistent-artifact-root", type=Path, required=True)
    validate.add_argument("--runtime-path", type=Path, required=True)
    validate.add_argument("--record", type=Path, required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--job-id", required=True)
    prepare.add_argument("--runtime-path", type=Path, required=True)
    prepare.add_argument("--record", type=Path, required=True)

    cleanup = subparsers.add_parser("cleanup")
    cleanup.add_argument("--job-id", required=True)
    cleanup.add_argument("--runtime-path", type=Path, required=True)
    cleanup.add_argument("--record", type=Path, required=True)

    arguments = parser.parse_args(argv)
    try:
        if arguments.operation == "validate":
            value = runtime_path_record(
                job_id=arguments.job_id,
                task_id=arguments.task_id,
                persistent_artifact_root=arguments.persistent_artifact_root,
            )
            if arguments.runtime_path != Path(value["runtime_directory"]):
                raise QualificationRuntimePathError(
                    "launcher runtime path differs from the validated path"
                )
            if not value["pass"]:
                raise QualificationRuntimePathError(
                    "runtime ZeroMQ path exceeds the safe maximum"
                )
        elif arguments.operation == "prepare":
            value = prepare_runtime_directory(
                arguments.runtime_path, job_id=arguments.job_id
            )
        else:
            value = cleanup_runtime_directory(
                arguments.runtime_path, job_id=arguments.job_id
            )
    except Exception as error:
        value = {
            "error": f"{type(error).__name__}: {error}",
            "job_id": arguments.job_id,
            "operation": arguments.operation,
            "pass": False,
            "runtime_path": str(arguments.runtime_path),
            "schema": "qwen32b-qualification-runtime-path-operation-v1",
        }
        _write(arguments.record, value)
        return 1
    _write(arguments.record, value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
