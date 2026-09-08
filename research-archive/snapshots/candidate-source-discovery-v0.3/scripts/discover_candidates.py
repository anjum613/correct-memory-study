#!/usr/bin/env python3
"""Capture, materialize, or verify the frozen candidate-discovery source."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.candidate_discovery import (
    CandidateDiscoveryError,
    capture_snapshot,
    load_query,
    materialize_snapshot,
    verify_snapshot,
)


DEFAULT_QUERY = ROOT / "benchmark-selection/discovery/v0.1/query.json"
DEFAULT_LEDGER = ROOT / "benchmark-selection/candidate-ledger.jsonl"


def _snapshot_path(query_path: Path) -> Path:
    query = load_query(query_path)
    return ROOT / str(query["snapshot_repository_path"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("capture", "materialize", "verify"))
    parser.add_argument("--query", type=Path, default=DEFAULT_QUERY)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    query_path = arguments.query.resolve()
    snapshot = (
        arguments.snapshot.resolve()
        if arguments.snapshot is not None
        else _snapshot_path(query_path)
    )
    try:
        if arguments.operation == "capture":
            result = capture_snapshot(
                query_path=query_path,
                snapshot_directory=snapshot,
            )
        elif arguments.operation == "materialize":
            result = materialize_snapshot(
                project_root=ROOT,
                query_path=query_path,
                snapshot_directory=snapshot,
                ledger_path=arguments.ledger.resolve(),
            )
        else:
            result = verify_snapshot(
                project_root=ROOT,
                query_path=query_path,
                snapshot_directory=snapshot,
                ledger_path=arguments.ledger.resolve(),
            )
    except CandidateDiscoveryError as error:
        parser_error = {"pass": False, "error": str(error)}
        print(json.dumps(parser_error, indent=2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
