#!/usr/bin/env python3
"""Prepare and finalize the bounded Devstral technical smoke."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.devstral_technical_smoke import (  # noqa: E402
    DevstralTechnicalSmokeError,
    authorization_probe,
    finalize_job,
    load_json,
    runtime_integrity_from_verifier,
    validate_completion,
    write_new_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight")
    preflight.add_argument("--verification", type=Path, required=True)
    preflight.add_argument("--output-directory", type=Path, required=True)
    authorization = commands.add_parser("authorization-probe")
    authorization.add_argument("--output", type=Path, required=True)
    complete = commands.add_parser("complete")
    complete.add_argument("--artifact-directory", type=Path, required=True)
    complete.add_argument("--runner-exit-code", type=int, required=True)
    complete.add_argument("--output", type=Path, required=True)
    finalize = commands.add_parser("finalize")
    finalize.add_argument("--artifact-directory", type=Path, required=True)
    finalize.add_argument("--runner-exit-code", type=int, required=True)
    arguments = parser.parse_args()

    try:
        if arguments.command == "preflight":
            record = runtime_integrity_from_verifier(
                ROOT, load_json(arguments.verification)
            )
            write_new_json(arguments.output_directory / "runtime-integrity.json", record)
            write_new_json(
                arguments.output_directory / "server-command.json",
                record["server_argv"],
            )
        elif arguments.command == "authorization-probe":
            record = authorization_probe()
            write_new_json(arguments.output, record)
        elif arguments.command == "finalize":
            record = finalize_job(
                arguments.artifact_directory,
                runner_exit_code=arguments.runner_exit_code,
            )
        else:
            finalize_job(
                arguments.artifact_directory,
                runner_exit_code=arguments.runner_exit_code,
            )
            record = validate_completion(
                arguments.artifact_directory,
                runner_exit_code=arguments.runner_exit_code,
            )
            write_new_json(arguments.output, record)
    except (DevstralTechnicalSmokeError, OSError, ValueError, KeyError) as error:
        print(f"DEVSTRAL_TECHNICAL_SMOKE_FAILURE: {error}", file=sys.stderr)
        return 1
    print(record["schema"])
    return 0 if record.get("pass") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
