#!/usr/bin/env python3
"""Verify the frozen human-review resolution for controlled synthetic v2."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
FINAL_ROOT = REPO_ROOT / "synthetic_triplets/controlled_v2_final"
MACHINE_MANIFEST_PATH = FINAL_ROOT / "cohort_manifest.json"
RESOLUTION_PATH = FINAL_ROOT / "human_review_resolution.json"

EXPECTED_MACHINE_MANIFEST_SHA256 = (
    "561291981224ec4b4f501365eab6fd0680ceb4425911a820c4f43ba1bcc8262c"
)
EXPECTED_RESOLUTION_SHA256 = (
    "9b7f4bfc6ac5111a5a9dc227c2d1df8fb2e552b18de91c79209915cc28487235"
)
EXPECTED_SOURCE_COMMIT = "25c30a16da3c2bbb06a8fe4949e7b115179bd3c3"
EXPECTED_SOURCE_TAG = "controlled-synthetic-v2-machine-cohort-v1"

MACHINE_FAMILY_IDS = (
    "F01",
    "F02",
    "F03",
    "F04",
    "F05",
    "F06",
    "F07",
    "F08",
    "F09",
    "R01",
    "F11",
    "F12",
    "R02",
    "F14",
    "F15",
    "F16",
    "F17",
    "F18",
    "F19",
    "F20",
)
REVIEW_1_REJECTED = ("F05", "F09", "F11", "F12", "R02", "F15", "F16", "F18")
REVIEW_1_PASSED = tuple(
    family_id for family_id in MACHINE_FAMILY_IDS if family_id not in REVIEW_1_REJECTED
)
PERMANENTLY_RETAINED = ("F01", "F02", "F04", "F08", "F17", "F20")
REVIEW_2_REJECTED = ("F03", "F06", "F07", "R01", "F14", "F19")
FAILED_CRITERIA = {
    "F03": (6, 7),
    "F05": (9,),
    "F06": (8,),
    "F07": (6, 8, 9),
    "F09": (8,),
    "R01": (9,),
    "F11": (6,),
    "F12": (8,),
    "R02": (5, 8),
    "F14": (8,),
    "F15": (8,),
    "F16": (9,),
    "F18": (8,),
    "F19": (6, 7, 8),
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"expected JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_resolution(
    resolution_path: Path = RESOLUTION_PATH,
    machine_manifest_path: Path = MACHINE_MANIFEST_PATH,
) -> dict[str, Any]:
    _require(
        _sha256(resolution_path) == EXPECTED_RESOLUTION_SHA256,
        "human-review resolution digest changed",
    )
    _require(
        _sha256(machine_manifest_path) == EXPECTED_MACHINE_MANIFEST_SHA256,
        "source machine-cohort manifest digest changed",
    )

    resolution = _read_object(resolution_path)
    machine = _read_object(machine_manifest_path)
    _require(
        resolution.get("schema_version")
        == "controlled-synthetic-v2-human-review-resolution/1",
        "human-review resolution schema changed",
    )
    _require(
        resolution.get("status") == "FROZEN_POST_HUMAN_REVIEW_COHORT_INCOMPLETE",
        "human-review resolution is not frozen and incomplete",
    )

    source = resolution.get("source_machine_cohort", {})
    _require(source.get("cohort_id") == machine.get("cohort_id"), "cohort id mismatch")
    _require(
        source.get("manifest_sha256") == EXPECTED_MACHINE_MANIFEST_SHA256,
        "recorded machine-manifest digest changed",
    )
    _require(source.get("git_commit") == EXPECTED_SOURCE_COMMIT, "source commit changed")
    _require(source.get("git_tag") == EXPECTED_SOURCE_TAG, "source tag changed")

    machine_rows = machine.get("families", [])
    machine_ids = tuple(row.get("family_id") for row in machine_rows)
    _require(machine_ids == MACHINE_FAMILY_IDS, "machine family order changed")
    machine_by_id = {row["family_id"]: row for row in machine_rows}

    reviewers = resolution.get("review_evidence", {}).get("reviewers", [])
    _require(len(reviewers) == 2, "expected exactly two reviewer summaries")
    first, second = reviewers
    _require(
        tuple(first.get("reviewed_family_ids", [])) == MACHINE_FAMILY_IDS,
        "reviewer 1 scope changed",
    )
    _require(
        tuple(first.get("passed_family_ids", [])) == REVIEW_1_PASSED,
        "reviewer 1 pass set changed",
    )
    _require(
        tuple(first.get("rejected_family_ids", [])) == REVIEW_1_REJECTED,
        "reviewer 1 rejection set changed",
    )
    _require(
        tuple(second.get("reviewed_family_ids", [])) == REVIEW_1_PASSED,
        "reviewer 2 scope is not reviewer 1's survivor set",
    )
    _require(
        tuple(second.get("passed_family_ids", [])) == PERMANENTLY_RETAINED,
        "permanent retained set changed",
    )
    _require(
        tuple(second.get("rejected_family_ids", [])) == REVIEW_2_REJECTED,
        "reviewer 2 rejection set changed",
    )
    _require(second.get("independent_review") is True, "reviewer 2 was not independent")
    _require(second.get("outcome_blind") is True, "reviewer 2 was not outcome blind")

    approval = resolution.get("resolution_approval", {})
    _require(
        approval.get("status") == "SIGNED_BY_PROJECT_OWNER",
        "project-owner approval is not signed",
    )
    _require(
        approval.get("signature_form")
        == "EXPLICIT_USER_ATTESTATION_IN_CODEX_WORKTREE_SESSION",
        "project-owner signature provenance changed",
    )
    _require(
        approval.get("cryptographic_signature_supplied") is False,
        "signature form is inaccurately marked cryptographic",
    )
    _require(
        tuple(approval.get("approved_retained_family_ids", []))
        == PERMANENTLY_RETAINED,
        "signed retained-family set changed",
    )

    retained_rows = resolution.get("retained_families", [])
    rejected_rows = resolution.get("rejected_families", [])
    retained_ids = tuple(row.get("family_id") for row in retained_rows)
    rejected_ids = tuple(row.get("family_id") for row in rejected_rows)
    _require(retained_ids == PERMANENTLY_RETAINED, "retained-family order changed")
    _require(set(rejected_ids) == set(FAILED_CRITERIA), "rejected-family set changed")
    _require(
        set(retained_ids).isdisjoint(rejected_ids),
        "a family is both retained and rejected",
    )
    _require(
        set(retained_ids) | set(rejected_ids) == set(MACHINE_FAMILY_IDS),
        "human decisions do not partition the machine cohort",
    )

    expected_stage = {
        **{family_id: "HUMAN_REVIEW_1" for family_id in REVIEW_1_REJECTED},
        **{family_id: "HUMAN_REVIEW_2" for family_id in REVIEW_2_REJECTED},
    }
    for row in retained_rows:
        family_id = row["family_id"]
        source_row = machine_by_id[family_id]
        _require(row.get("decision") == "PERMANENTLY_RETAINED", f"{family_id} changed")
        _require(row.get("original_slot") == source_row["slot"], f"{family_id} slot changed")
        _require(
            row.get("accepted_copy") == source_row["accepted_copy"],
            f"{family_id} artifact reference changed",
        )
    for row in rejected_rows:
        family_id = row["family_id"]
        source_row = machine_by_id[family_id]
        _require(row.get("decision") == "PERMANENTLY_REJECTED", f"{family_id} changed")
        _require(row.get("review_stage") == expected_stage[family_id], f"{family_id} stage changed")
        _require(
            tuple(row.get("failed_criteria", [])) == FAILED_CRITERIA[family_id],
            f"{family_id} failed criteria changed",
        )
        _require(bool(row.get("reason")), f"{family_id} rejection reason missing")
        _require(row.get("original_slot") == source_row["slot"], f"{family_id} slot changed")
        _require(
            row.get("accepted_copy") == source_row["accepted_copy"],
            f"{family_id} artifact reference changed",
        )

    counts = resolution.get("counts", {})
    _require(counts.get("machine_accepted") == 20, "machine count changed")
    _require(counts.get("reviewer_1_passed") == 12, "reviewer 1 pass count changed")
    _require(counts.get("reviewer_1_rejected") == 8, "reviewer 1 rejection count changed")
    _require(counts.get("permanently_retained") == 6, "retained count changed")
    _require(counts.get("permanently_rejected") == 14, "rejected count changed")
    _require(counts.get("reviewer_2_rejected") == 6, "reviewer 2 rejection count changed")

    disposition = resolution.get("cohort_disposition", {})
    _require(
        disposition.get("machine_cohort_20")
        == "REJECTED_BY_HUMAN_REVIEW_DO_NOT_TAG_AS_FINAL",
        "20-family disposition changed",
    )
    _require(
        disposition.get("reviewer_1_survivor_cohort_12")
        == "REJECTED_BY_SECOND_HUMAN_REVIEW_DO_NOT_TAG_AS_FINAL",
        "12-family disposition changed",
    )
    _require(
        disposition.get("permanent_retained_pool_6") == "FROZEN",
        "six-family pool is not frozen",
    )

    return {
        "status": resolution["status"],
        "machine_family_count": len(machine_ids),
        "permanently_retained": list(retained_ids),
        "permanently_rejected_count": len(rejected_ids),
        "resolution_sha256": _sha256(resolution_path),
        "source_manifest_sha256": _sha256(machine_manifest_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify the frozen resolution")
    args = parser.parse_args(argv)
    if not args.check:
        parser.error("--check is required; the frozen resolution cannot be rewritten")
    print(json.dumps(verify_resolution(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
