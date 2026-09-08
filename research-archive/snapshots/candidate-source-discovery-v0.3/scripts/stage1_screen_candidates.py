#!/usr/bin/env python3
"""Screen, apply, or verify Stage-1 static candidate evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.stage1_screening import (  # noqa: E402
    Stage1ScreeningError,
    apply_results_to_ledger,
    load_spec,
    screen_batch,
    verify_screening,
)


DEFAULT_SPEC = ROOT / "benchmark-selection/stage1/v0.1/inspection-spec.json"
DEFAULT_LEDGER = ROOT / "benchmark-selection/candidate-ledger.jsonl"


def _output_path(spec_path: Path) -> Path:
    return ROOT / str(load_spec(spec_path)["output_directory"])


def _head() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _require_clean() -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        raise Stage1ScreeningError("screen requires a clean pre-screening commit")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("screen", "apply-ledger", "verify"))
    parser.add_argument("--spec", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--scratch-parent", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    spec_path = arguments.spec.resolve()
    output = (
        arguments.output.resolve()
        if arguments.output is not None
        else _output_path(spec_path)
    )
    try:
        if arguments.operation == "screen":
            _require_clean()
            scratch_parent = (
                arguments.scratch_parent.resolve()
                if arguments.scratch_parent is not None
                else Path(tempfile.gettempdir())
            )
            result = screen_batch(
                project_root=ROOT,
                spec_path=spec_path,
                output_directory=output,
                method_commit=_head(),
                scratch_parent=scratch_parent,
            )
        elif arguments.operation == "apply-ledger":
            result = apply_results_to_ledger(
                project_root=ROOT,
                output_directory=output,
                ledger_path=arguments.ledger.resolve(),
            )
        else:
            result = verify_screening(
                project_root=ROOT,
                spec_path=spec_path,
                output_directory=output,
                ledger_path=arguments.ledger.resolve(),
            )
    except (Stage1ScreeningError, OSError, subprocess.SubprocessError) as error:
        print(json.dumps({"pass": False, "error": str(error)}, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
