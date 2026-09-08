#!/usr/bin/env python3
"""Assemble and verify the 20-family controlled-v2 machine-accepted cohort."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.controlled_v2_catalog import FAMILY_BY_ID as ORIGINAL_BY_ID  # noqa: E402
import scripts.freeze_controlled_v2_continuation as continuation_release  # noqa: E402
import scripts.freeze_controlled_v2_release as base_release  # noqa: E402
from scripts.reserve_catalog_v2 import FAMILY_BY_ID as RESERVE_BY_ID  # noqa: E402
import scripts.freeze_controlled_v2_reserve as reserve_release  # noqa: E402
from scripts.validate_controlled_triplet_v2 import validate_candidate  # noqa: E402
from scripts.validate_controlled_triplet_v2_reserve import (  # noqa: E402
    validate_candidate as validate_reserve_candidate,
)


ORIGINAL_ROOT = REPO_ROOT / "synthetic_triplets/controlled_v2"
RESERVE_ROOT = REPO_ROOT / "synthetic_triplets/controlled_v2_reserve"
FINAL_ROOT = REPO_ROOT / "synthetic_triplets/controlled_v2_final"
MANIFEST_PATH = FINAL_ROOT / "cohort_manifest.json"
ACCEPTED_ROOT = FINAL_ROOT / "accepted"
AI_REVIEW_PATH = FINAL_ROOT / "ai_semantic_review.json"

# Frozen after all constructors terminated. Ordering preserves the original slots;
# a retired slot is filled by the next reserve in its pre-frozen queue order.
SELECTED = (
    ("F01", 1, "original"),
    ("F02", 4, "continuation"),
    ("F03", 1, "original"),
    ("F04", 4, "continuation"),
    ("F05", 4, "continuation"),
    ("F06", 1, "original"),
    ("F07", 4, "continuation"),
    ("F08", 4, "continuation"),
    ("F09", 2, "original"),
    ("R01", 1, "reserve-for-F10"),
    ("F11", 1, "original"),
    ("F12", 2, "original"),
    ("R02", 1, "reserve-for-F13"),
    ("F14", 1, "original"),
    ("F15", 4, "continuation"),
    ("F16", 4, "continuation"),
    ("F17", 3, "original"),
    ("F18", 2, "original"),
    ("F19", 1, "original"),
    ("F20", 4, "continuation"),
)
RETIRED = {"F10": 8, "F13": 8}
UNUSED_RESERVES = ("R03", "R04", "R05")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def family_object(family_id: str):
    return RESERVE_BY_ID[family_id] if family_id.startswith("R") else ORIGINAL_BY_ID[family_id]


def acquisition_root(family_id: str) -> Path:
    cohort = RESERVE_ROOT if family_id.startswith("R") else ORIGINAL_ROOT
    return cohort / "acquisitions/raw" / family_id


def candidate_root(family_id: str, attempt: int) -> Path:
    return acquisition_root(family_id) / f"attempt-{attempt:03d}/workspace/candidate"


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def attempt_numbers(family_id: str) -> list[int]:
    result: list[int] = []
    root = acquisition_root(family_id)
    if not root.exists():
        return result
    for path in sorted(root.glob("attempt-*")):
        try:
            number = int(path.name.split("-", 1)[1])
        except (IndexError, ValueError) as error:
            raise ValueError(f"malformed attempt directory: {path}") from error
        if not (path / "record/outcome.json").is_file():
            raise ValueError(f"incomplete attempt: {path}")
        result.append(number)
    if result != list(range(1, len(result) + 1)):
        raise ValueError(f"non-contiguous attempts for {family_id}: {result}")
    return result


def raw_tree_digest(root: Path) -> tuple[int, int, str]:
    files = sorted(path for path in root.rglob("*") if path.is_file())
    digest = hashlib.sha256()
    size = 0
    for path in files:
        data = path.read_bytes()
        size += len(data)
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
    return len(files), size, digest.hexdigest()


def protocol_for(family_id: str, attempt: int) -> dict[str, str]:
    if family_id.startswith("R"):
        return {
            "kind": "reserve",
            "release_tag": "controlled-synthetic-v2-reserve-v2",
            "inventory_sha256": reserve_release.verify_release()["inventory_sha256"],
        }
    if attempt <= 3:
        return {
            "kind": "original",
            "release_tag": "controlled-synthetic-v2-filter-v1",
            "inventory_sha256": base_release.verify_release()["inventory_sha256"],
        }
    return {
        "kind": "continuation",
        "release_tag": "controlled-synthetic-v2-continuation-v1",
        "inventory_sha256": continuation_release.verify_release()["inventory_sha256"],
    }


def validate_selection() -> list[dict[str, Any]]:
    if len(SELECTED) != 20 or len({row[0] for row in SELECTED}) != 20:
        raise ValueError("selection must contain exactly 20 unique family ids")
    selected_ids = {row[0] for row in SELECTED}
    expected_original = set(ORIGINAL_BY_ID) - set(RETIRED)
    if selected_ids & set(ORIGINAL_BY_ID) != expected_original:
        raise ValueError("selected original families do not equal originals minus retired ids")
    if selected_ids & set(RESERVE_BY_ID) != {"R01", "R02"}:
        raise ValueError("reserve substitution order changed")

    rows: list[dict[str, Any]] = []
    seen_hashes: dict[str, dict[str, str]] = {
        "B": {},
        "feature_patch": {},
        "security_patch": {},
        "candidate_tree": {},
    }
    for slot, (family_id, attempt, selection_source) in enumerate(SELECTED, 1):
        attempts = attempt_numbers(family_id)
        if not attempts or attempts[-1] != attempt:
            raise ValueError(f"attempts continued after acceptance for {family_id}: {attempts}")
        root = acquisition_root(family_id) / f"attempt-{attempt:03d}"
        outcome = read_json(root / "record/outcome.json")
        recorded_validation = read_json(root / "record/validation.json")
        if outcome.get("machine_accepted") is not True:
            raise ValueError(f"selected outcome was not accepted: {family_id}")
        if recorded_validation.get("terminal_reason") != "COMPLETE_ACCEPT":
            raise ValueError(f"recorded validation did not accept: {family_id}")
        if len(recorded_validation.get("checks", [])) != 21:
            raise ValueError(f"recorded check count changed: {family_id}")
        if any(not check.get("passed") for check in recorded_validation["checks"]):
            raise ValueError(f"recorded failed check in selected candidate: {family_id}")

        candidate = candidate_root(family_id, attempt)
        fresh = (
            validate_reserve_candidate(family_id, candidate)
            if family_id.startswith("R")
            else validate_candidate(family_id, candidate)
        )
        if fresh.get("terminal_reason") != "COMPLETE_ACCEPT" or len(fresh.get("checks", [])) != 21:
            raise ValueError(f"fresh validation failed: {family_id}")

        file_map = {
            "B": candidate / "B/app/service.py",
            "feature_patch": candidate / "feature.patch",
            "security_patch": candidate / "security.patch",
        }
        hashes = {name: sha256_file(path) for name, path in file_map.items()}
        tree_material = b"\0".join(
            name.encode() + b"\0" + file_map[name].read_bytes() for name in sorted(file_map)
        )
        hashes["candidate_tree"] = sha256_bytes(tree_material)
        for name, digest in hashes.items():
            duplicate = seen_hashes[name].get(digest)
            if duplicate:
                raise ValueError(f"duplicate {name}: {duplicate} and {family_id}")
            seen_hashes[name][digest] = family_id

        item = family_object(family_id)
        accepted_relative = f"accepted/{slot:02d}-{family_id.lower()}-{item.slug}"
        rows.append(
            {
                "slot": slot,
                "family_id": family_id,
                "slug": item.slug,
                "title": item.title,
                "mechanism": item.mechanism,
                "mismatch_axis": item.mismatch_axis,
                "accepted_attempt": f"attempt-{attempt:03d}",
                "selection_source": selection_source,
                "protocol": protocol_for(family_id, attempt),
                "candidate_source": candidate.relative_to(REPO_ROOT).as_posix(),
                "accepted_copy": accepted_relative,
                "candidate_sha256": hashes,
                "recorded_validation_sha256": sha256_file(root / "record/validation.json"),
                "fresh_validation": "COMPLETE_ACCEPT_21_OF_21",
                "constructor_completed_at_utc": outcome["completed_at_utc"],
            }
        )

    mechanisms = [row["mechanism"] for row in rows]
    axes = [row["mismatch_axis"] for row in rows]
    if len(set(mechanisms)) != 20 or len(set(axes)) != 20:
        raise ValueError("selected mechanisms or mismatch axes are not unique")
    return rows


def validate_retirement_and_unused_reserves() -> list[dict[str, Any]]:
    retired_rows: list[dict[str, Any]] = []
    for family_id, expected_attempts in RETIRED.items():
        attempts = attempt_numbers(family_id)
        if attempts != list(range(1, expected_attempts + 1)):
            raise ValueError(f"retired attempt sequence changed: {family_id}")
        accepted = []
        for number in attempts:
            outcome = read_json(
                acquisition_root(family_id)
                / f"attempt-{number:03d}/record/outcome.json"
            )
            if outcome.get("machine_accepted") is True:
                accepted.append(number)
        if accepted:
            raise ValueError(f"retired family has accepted attempts: {family_id} {accepted}")
        retired_rows.append(
            {
                "family_id": family_id,
                "attempts_preserved": expected_attempts,
                "reason": "EXHAUSTED_CONTINUATION",
            }
        )
    for family_id in UNUSED_RESERVES:
        if attempt_numbers(family_id):
            raise ValueError(f"unused reserve was run after cohort completion: {family_id}")
    return retired_rows


def expected_accepted_files(rows: list[dict[str, Any]]) -> dict[str, bytes]:
    expected: dict[str, bytes] = {}
    for row in rows:
        family_id = row["family_id"]
        attempt = int(row["accepted_attempt"].split("-")[1])
        candidate = candidate_root(family_id, attempt)
        prefix = row["accepted_copy"]
        expected[f"{prefix}/B/app/service.py"] = (candidate / "B/app/service.py").read_bytes()
        expected[f"{prefix}/feature.patch"] = (candidate / "feature.patch").read_bytes()
        expected[f"{prefix}/security.patch"] = (candidate / "security.patch").read_bytes()
        item = family_object(family_id)
        expected[f"{prefix}/spec.json"] = json_bytes(item.public_spec())
        expected[f"{prefix}/provenance.json"] = json_bytes(row)
    return expected


def manifest() -> tuple[dict[str, Any], dict[str, bytes]]:
    base = base_release.verify_release()
    continuation = continuation_release.verify_release()
    reserve = reserve_release.verify_release()
    rows = validate_selection()
    retired = validate_retirement_and_unused_reserves()
    ai_review = read_json(AI_REVIEW_PATH)
    reviewed = ai_review.get("families", [])
    if ai_review.get("status") != "PASS_HUMAN_REVIEW_STILL_REQUIRED":
        raise ValueError("AI semantic review has not passed")
    if [item.get("family_id") for item in reviewed] != [item[0] for item in SELECTED]:
        raise ValueError("AI semantic review family order differs from the selected cohort")
    if any(item.get("result") != "PASS" for item in reviewed):
        raise ValueError("AI semantic review contains a non-pass result")
    original_raw = raw_tree_digest(ORIGINAL_ROOT / "acquisitions/raw")
    reserve_raw = raw_tree_digest(RESERVE_ROOT / "acquisitions/raw")
    value = {
        "schema_version": "controlled-synthetic-v2-machine-cohort/1",
        "status": "MACHINE_COMPLETE_AI_SEMANTIC_PASS_HUMAN_REVIEW_PENDING",
        "cohort_id": "controlled-synthetic-v2-machine-cohort-v1",
        "family_count": 20,
        "original_family_count": 18,
        "reserve_family_count": 2,
        "machine_accept_count": 20,
        "fresh_revalidation_pass_count": 20,
        "checks_per_family": 21,
        "duplicate_candidate_hashes": 0,
        "unique_mechanism_count": 20,
        "unique_mismatch_axis_count": 20,
        "assembled_at_utc": max(row["constructor_completed_at_utc"] for row in rows),
        "release_chain": {
            "base_filter": {
                "tag": "controlled-synthetic-v2-filter-v1",
                "inventory_sha256": base["inventory_sha256"],
            },
            "continuation": {
                "tag": "controlled-synthetic-v2-continuation-v1",
                "inventory_sha256": continuation["inventory_sha256"],
            },
            "reserve": {
                "tag": "controlled-synthetic-v2-reserve-v2",
                "inventory_sha256": reserve["inventory_sha256"],
            },
        },
        "raw_acquisition_trees": {
            "original_and_continuation": {
                "file_count": original_raw[0],
                "bytes": original_raw[1],
                "sha256": original_raw[2],
            },
            "reserve": {
                "file_count": reserve_raw[0],
                "bytes": reserve_raw[1],
                "sha256": reserve_raw[2],
            },
        },
        "retired_families": retired,
        "unused_frozen_reserves": list(UNUSED_RESERVES),
        "families": rows,
        "ai_semantic_review": {
            "status": ai_review["status"],
            "reviewed_family_count": len(reviewed),
            "path": AI_REVIEW_PATH.relative_to(REPO_ROOT).as_posix(),
            "sha256": sha256_file(AI_REVIEW_PATH),
        },
        "human_blinded_review": "PENDING",
        "confirmatory_evaluation": "BLOCKED_UNTIL_HUMAN_REVIEW_AND_EVALUATION_FREEZE",
    }
    return value, expected_accepted_files(rows)


def write_new_or_verify(path: Path, payload: bytes, *, write: bool) -> None:
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.read_bytes() != payload:
            raise FileExistsError(f"refusing to overwrite differing final artifact: {path}")
        if not path.exists():
            path.write_bytes(payload)
    elif not path.is_file() or path.read_bytes() != payload:
        raise ValueError(f"final artifact missing or changed: {path}")


def run(*, write: bool) -> dict[str, Any]:
    value, accepted = manifest()
    write_new_or_verify(MANIFEST_PATH, json_bytes(value), write=write)
    for relative, payload in accepted.items():
        write_new_or_verify(FINAL_ROOT / relative, payload, write=write)
    expected_paths = {MANIFEST_PATH.relative_to(FINAL_ROOT).as_posix(), *accepted}
    if ACCEPTED_ROOT.exists():
        actual = {
            path.relative_to(FINAL_ROOT).as_posix()
            for path in ACCEPTED_ROOT.rglob("*")
            if path.is_file()
        }
        unexpected = sorted(actual - set(accepted))
        if unexpected:
            raise ValueError(f"unexpected final accepted artifacts: {unexpected[:3]}")
    return {
        "status": value["status"],
        "family_count": value["family_count"],
        "machine_accept_count": value["machine_accept_count"],
        "fresh_revalidation_pass_count": value["fresh_revalidation_pass_count"],
        "accepted_artifact_count": len(accepted),
        "manifest_sha256": sha256_bytes(json_bytes(value)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    print(json.dumps(run(write=args.write), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
