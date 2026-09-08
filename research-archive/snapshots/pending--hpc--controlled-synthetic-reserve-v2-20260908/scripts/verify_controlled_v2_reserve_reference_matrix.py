#!/usr/bin/env python3
"""Verify that each frozen reserve specification has a satisfying B/U/R witness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.reserve_catalog_v2 import FAMILIES, REFERENCE_STATES  # noqa: E402
from scripts.validate_controlled_triplet_v2 import make_patch  # noqa: E402
from scripts.validate_controlled_triplet_v2_reserve import validate_candidate  # noqa: E402


def verify() -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for item in FAMILIES:
        reference = REFERENCE_STATES[item.family_id]
        with tempfile.TemporaryDirectory(prefix=f"reserve-{item.family_id.lower()}-") as temp:
            candidate = Path(temp)
            service = candidate / "B/app/service.py"
            service.parent.mkdir(parents=True)
            service.write_text(reference.b, encoding="utf-8")
            (candidate / "feature.patch").write_text(
                make_patch(reference.b, reference.u), encoding="utf-8"
            )
            (candidate / "security.patch").write_text(
                make_patch(reference.u, reference.r), encoding="utf-8"
            )
            report = validate_candidate(item.family_id, candidate)
        rows.append(
            {
                "family_id": item.family_id,
                "terminal_reason": report["terminal_reason"],
                "check_count": len(report["checks"]),
                "failed_checks": [
                    check["name"] for check in report["checks"] if not check["passed"]
                ],
            }
        )
    return {
        "schema_version": "controlled-synthetic-v2-reserve-reference-matrix/1",
        "all_passed": all(row["terminal_reason"] == "COMPLETE_ACCEPT" for row in rows),
        "family_count": len(rows),
        "families": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args(argv)
    result = verify()
    if args.compact:
        print(
            json.dumps(
                {
                    "all_passed": result["all_passed"],
                    "family_count": result["family_count"],
                    "failed": [
                        row for row in result["families"] if row["terminal_reason"] != "COMPLETE_ACCEPT"
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
