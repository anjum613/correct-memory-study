#!/usr/bin/env python3
"""Validate and finalize the non-confirmatory Qwen32B technical smoke."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.qwen32b_final_smoke import (  # noqa: E402
    PORT,
    QwenFinalSmokeError,
    validate_completion,
    validate_runtime_integrity,
    write_new_json,
    write_preflight,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    preflight = commands.add_parser("preflight")
    preflight.add_argument("--project-root", type=Path, default=ROOT)
    preflight.add_argument("--output-directory", type=Path, required=True)
    preflight.add_argument("--port", type=int, default=PORT)

    runtime = commands.add_parser("runtime-integrity")
    runtime.add_argument("--fingerprint", type=Path, required=True)
    runtime.add_argument("--content", type=Path, required=True)
    runtime.add_argument("--output", type=Path, required=True)

    complete = commands.add_parser("complete")
    complete.add_argument("--run-artifact", type=Path, required=True)
    complete.add_argument("--health-status", type=Path, required=True)
    complete.add_argument("--models-response", type=Path, required=True)
    complete.add_argument("--runtime-integrity", type=Path, required=True)
    complete.add_argument("--server-cleanup", type=Path, required=True)
    complete.add_argument("--runner-exit-code", type=int, required=True)
    complete.add_argument("--output", type=Path, required=True)

    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "preflight":
            record = write_preflight(
                arguments.project_root,
                arguments.output_directory,
                port=arguments.port,
            )
        elif arguments.command == "runtime-integrity":
            record = validate_runtime_integrity(
                arguments.fingerprint, arguments.content
            )
            write_new_json(arguments.output, record)
        else:
            record = validate_completion(
                arguments.run_artifact,
                health_status_path=arguments.health_status,
                models_response_path=arguments.models_response,
                runtime_integrity_path=arguments.runtime_integrity,
                server_cleanup_path=arguments.server_cleanup,
                runner_exit_code=arguments.runner_exit_code,
            )
            write_new_json(arguments.output, record)
    except (OSError, ValueError, QwenFinalSmokeError) as error:
        print(f"QWEN32B_FINAL_SMOKE_FAILURE: {error}", file=sys.stderr)
        return 1
    print(record["schema"])
    return 0 if record.get("pass") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
