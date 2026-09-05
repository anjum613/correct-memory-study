#!/usr/bin/env python3
"""Check clarification provenance only; never admit a candidate or launch work."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELATIVE = Path("protocols/controlled-synthetic-v3-x02-x22-clarification-v1")
ORDER = [f"X{i:02d}" for i in range(1, 29)]
SPEC = "synthetic_triplets/controlled_v3_expansion/family_specs.json"
PROTOCOL = "synthetic_triplets/controlled_v3_expansion/protocol.json"
LEDGER = "synthetic_triplets/controlled_v3_expansion/admission_ledger.json"
SPEC_SHA256 = "dd1665df9aa51bdf4cc52202f37ebbc98b680f1f97c97787dfd92435454a8df5"
PROTOCOL_SHA256 = "6cc383a3a6ab6bea1decf991c835fcfad47becd508462ef31ed47e34fa8c7994"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(root: Path, relative: str | Path) -> dict:
    return json.loads((root / relative).read_text())


def checked_file(root: Path, relative: str, expected: str) -> None:
    path = root / relative
    require(not Path(relative).is_absolute(), "absolute inventory path")
    require(".." not in Path(relative).parts, "parent inventory path")
    require(path.resolve().is_relative_to(root.resolve()), "inventory escapes root")
    require(path.is_file() and not path.is_symlink(), f"missing/nonregular file: {relative}")
    require(digest(path) == expected, f"content changed: {relative}")


def inspect(root: Path = ROOT, expected_manifest_sha256: str | None = None) -> dict:
    manifest_path = root / RELATIVE / "manifest.json"
    if expected_manifest_sha256 is not None:
        require(digest(manifest_path) == expected_manifest_sha256, "manifest digest changed")
    manifest = read(root, RELATIVE / "manifest.json")
    require(manifest["status"] == "SPECIFICATION_CLARIFICATION_ONLY", "incorrect release claim")
    require(manifest["construction_authorized"] is False, "construction must remain blocked")
    require(manifest["behavioral_validator_complete"] is False, "behavioral claim not established")
    for relative, expected in manifest["inventory"].items():
        checked_file(root, relative, expected)
    require(manifest["inventoried_file_count"] == len(manifest["inventory"]), "inventory count")

    preservation = read(root, RELATIVE / "preserved_file_inventory.json")
    require(preservation["file_count"] == len(preservation["inventory"]) == 572, "baseline count")
    for relative, record in preservation["inventory"].items():
        checked_file(root, relative, record["sha256"])
        require((root / relative).stat().st_size == record["bytes"], "baseline byte count")
    checked_file(root, SPEC, SPEC_SHA256)
    checked_file(root, PROTOCOL, PROTOCOL_SHA256)

    amendment = read(root, RELATIVE / "amendment.json")
    require(amendment["affected_families"] == ["X02", "X22"], "amendment scope changed")
    require(amendment["family_order"] == ORDER, "family order changed")
    require(amendment["constructor_attempt_limit_per_family"] == 4, "attempt cap changed")
    require(amendment["unaffected_families"] == [f for f in ORDER if f not in ("X02", "X22")], "other families changed")
    require(amendment["process_all_28_and_retain_every_admissible_family"] is True, "stopping amendment lost")
    for relative, expected in amendment["preserved_anchors"].items():
        checked_file(root, relative, expected)
    specs = read(root, SPEC)["specifications"]
    require([row["family_id"] for row in specs] == ORDER, "frozen order changed")
    require(all(row["constructor_attempt_limit"] == 4 for row in specs), "frozen cap changed")

    ledger = read(root, LEDGER)
    require(ledger["families"] == [], "recorded constructor/admission activity is not zero")
    require(ledger["evaluated_agent_outcomes_observed"] is False, "recorded outcome observation")
    require(ledger["agent_experiment_frozen"] is False, "unexpected experiment freeze")
    return {
        "status": "AMENDMENT_INTEGRITY_VALID_BEHAVIORAL_RELEASE_PENDING",
        "amendment_id": amendment["amendment_id"],
        "manifest_sha256": digest(manifest_path),
        "preserved_files_verified": 572,
        "original_28_specifications_byte_identical": True,
        "other_26_specifications_amended": False,
        "recorded_constructor_attempts": 0,
        "recorded_evaluated_agent_outcomes_observed": False,
        "reference_matrices_established_by_this_check": 0,
        "human_reviews_performed_by_this_check": 0,
        "behavioral_validator_complete": False,
        "construction_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-manifest-sha256")
    args = parser.parse_args(argv)
    try:
        report = inspect(expected_manifest_sha256=args.expected_manifest_sha256)
    except (KeyError, TypeError, ValueError, OSError) as error:
        print(json.dumps({"status": "INVALID_CLARIFICATION_PROVENANCE", "error": str(error)}))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0  # Provenance success ONLY; report explicitly forbids construction.


if __name__ == "__main__":
    raise SystemExit(main())
