#!/usr/bin/env python3
"""Portable standard-library check that all 20 frozen reference matrices hold."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.controlled_v2_catalog import FAMILIES, REFERENCE_STATES  # noqa: E402
from scripts.validate_controlled_triplet_v2 import make_patch, validate_candidate  # noqa: E402


def write_reference(root: Path, family_id: str) -> Path:
    reference = REFERENCE_STATES[family_id]
    candidate = root / family_id
    service = candidate / "B/app/service.py"
    service.parent.mkdir(parents=True)
    service.write_text(reference.b, encoding="utf-8")
    (candidate / "feature.patch").write_text(
        make_patch(reference.b, reference.u), encoding="utf-8"
    )
    (candidate / "security.patch").write_text(
        make_patch(reference.u, reference.r), encoding="utf-8"
    )
    return candidate


def verify() -> dict[str, object]:
    rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="controlled-v2-reference-") as temp:
        root = Path(temp)
        for family in FAMILIES:
            report = validate_candidate(
                family.family_id, write_reference(root, family.family_id)
            )
            rows.append(
                {
                    "family_id": family.family_id,
                    "terminal_reason": report["terminal_reason"],
                    "failed_checks": [
                        item["name"] for item in report["checks"] if not item["passed"]
                    ],
                }
            )
    passed = all(row["terminal_reason"] == "COMPLETE_ACCEPT" for row in rows)
    return {
        "schema_version": "controlled-synthetic-v2-reference-matrix-check/1",
        "family_count": len(rows),
        "complete_accept_count": sum(
            row["terminal_reason"] == "COMPLETE_ACCEPT" for row in rows
        ),
        "passed": passed,
        "families": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args(argv)
    report = verify()
    print(json.dumps(report, indent=None if args.compact else 2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
