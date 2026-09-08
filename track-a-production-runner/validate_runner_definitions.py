#!/usr/bin/env python3
"""Validate frozen Track A transition, recovery, and test coverage definitions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import track_a_runner_v2 as runner  # noqa: E402


def validate_coverage() -> dict[str, int | str | bool]:
    value = runner.validate_coverage_manifest()
    return {
        "pass": True,
        "schema": value["schema"],
        "scenario_count": len(value["required_scenarios"]),
        "state_count": len(value["state_coverage"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--component",
        choices=("all", "transitions", "recoveries", "coverage"),
        default="all",
    )
    arguments = parser.parse_args()
    output: dict[str, object] = {"pass": True}
    try:
        if arguments.component in {"all", "transitions", "recoveries"}:
            matrix, registry = runner.validate_transition_definitions()
            if arguments.component in {"all", "transitions"}:
                output["transitions"] = {
                    "schema": matrix["schema"],
                    "state_count": len(matrix["states"]),
                }
            if arguments.component in {"all", "recoveries"}:
                output["recoveries"] = {
                    "schema": registry["schema"],
                    "recovery_count": len(registry["recoveries"]),
                }
        if arguments.component in {"all", "coverage"}:
            output["coverage"] = validate_coverage()
    except (OSError, ValueError, runner.RunnerError) as error:
        print(json.dumps({"pass": False, "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
