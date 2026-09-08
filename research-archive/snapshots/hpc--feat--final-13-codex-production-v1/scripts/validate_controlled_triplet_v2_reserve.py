#!/usr/bin/env python3
"""Validate reserve candidates with the unchanged controlled-v2 admission logic."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.reserve_catalog_v2 import FAMILY_BY_ID  # noqa: E402
import scripts.validate_controlled_triplet_v2 as base  # noqa: E402


def validate_candidate(family_id: str, candidate_dir: Path) -> dict[str, object]:
    """Route a reserve family through the frozen validator implementation."""

    original = base.FAMILY_BY_ID
    base.FAMILY_BY_ID = FAMILY_BY_ID
    try:
        report = base.validate_candidate(family_id, candidate_dir)
    finally:
        base.FAMILY_BY_ID = original
    report["validator_implementation"] = "scripts/validate_controlled_triplet_v2.py"
    report["reserve_catalog_adapter_only"] = True
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("family_id", choices=sorted(FAMILY_BY_ID))
    parser.add_argument("candidate_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        report = validate_candidate(args.family_id, args.candidate_dir)
    except (base.AdmissionError, FileNotFoundError, OSError, UnicodeError) as error:
        report = {
            "schema_version": "controlled-synthetic-v2-admission/1",
            "family_id": args.family_id,
            "terminal_reason": "REJECT",
            "machine_accepted": False,
            "human_semantic_review_required": True,
            "fatal_error": str(error),
            "checks": [],
            "validator_implementation": "scripts/validate_controlled_triplet_v2.py",
            "reserve_catalog_adapter_only": True,
        }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if report["machine_accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
