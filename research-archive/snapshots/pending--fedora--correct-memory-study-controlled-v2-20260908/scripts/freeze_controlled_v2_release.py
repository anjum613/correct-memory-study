#!/usr/bin/env python3
"""Create or verify the content-addressed pre-construction v2 filter release."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
COHORT_ROOT = REPO_ROOT / "synthetic_triplets/controlled_v2"
RELEASE_PATH = COHORT_ROOT / "filter_release.json"
RELEASE_TAG = "controlled-synthetic-v2-filter-v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def released_paths() -> list[Path]:
    paths: set[Path] = set()
    for pattern in (
        "scripts/controlled_v2_*.py",
        "scripts/build_controlled_v2_condition_envelopes.py",
        "scripts/check_controlled_v2_public.py",
        "scripts/freeze_controlled_v2_release.py",
        "scripts/materialize_controlled_v2.py",
        "scripts/run_controlled_v2_constructors.py",
        "scripts/validate_controlled_triplet_v2.py",
        "scripts/verify_controlled_v2_reference_matrix.py",
        "tests/test_controlled_v2_*.py",
    ):
        paths.update(path for path in REPO_ROOT.glob(pattern) if path.is_file())
    for path in COHORT_ROOT.rglob("*"):
        if not path.is_file() or path == RELEASE_PATH:
            continue
        relative = path.relative_to(COHORT_ROOT)
        if relative.parts and relative.parts[0] in {"acquisitions", "reviews"}:
            continue
        paths.add(path)
    return sorted(paths)


def inventory() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in released_paths():
        relative = path.relative_to(REPO_ROOT).as_posix()
        result[relative] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
    return result


def inventory_sha256(files: dict[str, dict[str, Any]]) -> str:
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def run_checks() -> dict[str, Any]:
    commands = [
        [sys.executable, "scripts/materialize_controlled_v2.py", "--check"],
        [sys.executable, "scripts/verify_controlled_v2_reference_matrix.py", "--compact"],
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_controlled_v2_validator.py",
            "tests/test_controlled_v2_runner.py",
            "tests/test_controlled_v2_conditions.py",
            "tests/test_controlled_v2_release.py",
        ],
    ]
    records: list[dict[str, Any]] = []
    for command in commands:
        process = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        record = {
            "command": command,
            "returncode": process.returncode,
            "stdout": process.stdout,
            "stderr": process.stderr,
        }
        count = re.search(r"(\d+) passed", process.stdout + process.stderr)
        if count:
            record["observed_passed_tests"] = int(count.group(1))
        records.append(record)
        if process.returncode:
            raise RuntimeError(f"pre-freeze check failed: {' '.join(command)}")
    return {"checks": records, "all_passed": True}


def acquisitions_exist() -> bool:
    root = COHORT_ROOT / "acquisitions"
    return root.exists() and any(path.is_file() for path in root.rglob("*"))


def create_release() -> dict[str, Any]:
    if RELEASE_PATH.exists():
        raise FileExistsError(f"refusing to overwrite release: {RELEASE_PATH}")
    if acquisitions_exist():
        raise RuntimeError("constructor acquisitions already exist")
    validation = run_checks()
    files = inventory()
    family_specs = sorted(
        path.stem for path in (COHORT_ROOT / "family_specs").glob("F*.json")
    )
    if family_specs != [f"F{index:02d}" for index in range(1, 21)]:
        raise RuntimeError("expected exactly 20 materialized family specifications")
    return {
        "schema_version": "controlled-synthetic-v2-filter-release/1",
        "status": "FROZEN_PRE_CONSTRUCTION",
        "frozen_at_utc": utc_now(),
        "release_tag": RELEASE_TAG,
        "family_count": 20,
        "family_ids": family_specs,
        "constructor_candidates_existed_at_release": False,
        "constructor_run_records_existed_at_release": False,
        "evaluated_agent_runs_existed_at_release": False,
        "first_pass_attempt_limit": 3,
        "prospective_B_security_floor": True,
        "files": files,
        "inventory_sha256": inventory_sha256(files),
        "pre_freeze_validation": validation,
    }


def verify_release() -> dict[str, Any]:
    value = json.loads(RELEASE_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("release must be a JSON object")
    if value.get("schema_version") != "controlled-synthetic-v2-filter-release/1":
        raise ValueError("release schema mismatch")
    if value.get("status") != "FROZEN_PRE_CONSTRUCTION":
        raise ValueError("release status mismatch")
    if value.get("release_tag") != RELEASE_TAG:
        raise ValueError("release tag mismatch")
    expected = inventory()
    if value.get("files") != expected:
        raise ValueError("released file inventory no longer matches the tree")
    if value.get("inventory_sha256") != inventory_sha256(expected):
        raise ValueError("release inventory digest mismatch")
    if value.get("family_ids") != [f"F{index:02d}" for index in range(1, 21)]:
        raise ValueError("release family ids mismatch")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.write:
        release = create_release()
        payload = (json.dumps(release, indent=2, sort_keys=True) + "\n").encode()
        RELEASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with RELEASE_PATH.open("xb") as handle:
            handle.write(payload)
    else:
        release = verify_release()
    print(
        json.dumps(
            {
                "status": release["status"],
                "family_count": release["family_count"],
                "file_count": len(release["files"]),
                "inventory_sha256": release["inventory_sha256"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
