#!/usr/bin/env python3
"""Create or verify the content-addressed controlled-v2 continuation release."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTINUATION_ROOT = REPO_ROOT / "synthetic_triplets/controlled_v2_continuation"
BASE_ROOT = REPO_ROOT / "synthetic_triplets/controlled_v2"
RELEASE_PATH = CONTINUATION_ROOT / "continuation_release.json"
RELEASE_TAG = "controlled-synthetic-v2-continuation-v1"
BASE_RELEASE_PATH = BASE_ROOT / "filter_release.json"
BASE_RELEASE_TAG = "controlled-synthetic-v2-filter-v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def released_paths() -> list[Path]:
    relative = (
        "scripts/freeze_controlled_v2_continuation.py",
        "scripts/run_controlled_v2_continuation.py",
        "tests/test_construction_continuation_v2.py",
        "synthetic_triplets/controlled_v2_continuation/continuation_plan.json",
        "synthetic_triplets/controlled_v2_continuation/continuation_prompt.md",
        "synthetic_triplets/controlled_v2/filter_release.json",
    )
    paths = [REPO_ROOT / item for item in relative]
    missing = [str(path.relative_to(REPO_ROOT)) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"continuation release inputs missing: {missing}")
    return sorted(paths)


def inventory() -> dict[str, dict[str, Any]]:
    return {
        path.relative_to(REPO_ROOT).as_posix(): {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in released_paths()
    }


def inventory_sha256(files: dict[str, dict[str, Any]]) -> str:
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def read_base_release() -> dict[str, Any]:
    value = json.loads(BASE_RELEASE_PATH.read_text(encoding="utf-8"))
    if value.get("schema_version") != "controlled-synthetic-v2-filter-release/1":
        raise ValueError("base filter release schema mismatch")
    if value.get("release_tag") != BASE_RELEASE_TAG:
        raise ValueError("base filter release tag mismatch")
    return value


def continuation_attempts_exist() -> bool:
    root = BASE_ROOT / "acquisitions/raw"
    return any(root.glob("F*/attempt-00[4-8]")) if root.exists() else False


def run_checks() -> list[dict[str, Any]]:
    commands = [
        [sys.executable, "scripts/freeze_controlled_v2_release.py", "--check"],
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/test_construction_continuation_v2.py",
            "tests/test_controlled_v2_runner.py",
            "tests/test_controlled_v2_validator.py",
        ],
    ]
    records: list[dict[str, Any]] = []
    for command in commands:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        record = {
            "command": command,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
        records.append(record)
        if completed.returncode:
            raise RuntimeError(f"continuation pre-freeze check failed: {' '.join(command)}")
    return records


def create_release() -> dict[str, Any]:
    if RELEASE_PATH.exists():
        raise FileExistsError(f"refusing to overwrite release: {RELEASE_PATH}")
    if continuation_attempts_exist():
        raise RuntimeError("continuation attempts already exist")
    base = read_base_release()
    checks = run_checks()
    files = inventory()
    return {
        "schema_version": "controlled-synthetic-v2-continuation-release/1",
        "status": "FROZEN_BEFORE_CONTINUATION_ATTEMPTS",
        "frozen_at_utc": utc_now(),
        "release_tag": RELEASE_TAG,
        "base_filter_release_tag": BASE_RELEASE_TAG,
        "base_filter_inventory_sha256": base["inventory_sha256"],
        "family_count": 20,
        "continuation_attempt_range": [4, 8],
        "accepted_families_are_skipped": True,
        "prior_attempt_feedback_exposed": False,
        "validator_or_family_inputs_changed": False,
        "continuation_attempts_existed_at_release": False,
        "files": files,
        "inventory_sha256": inventory_sha256(files),
        "pre_freeze_validation": {"all_passed": True, "checks": checks},
    }


def verify_release() -> dict[str, Any]:
    value = json.loads(RELEASE_PATH.read_text(encoding="utf-8"))
    if value.get("schema_version") != "controlled-synthetic-v2-continuation-release/1":
        raise ValueError("continuation release schema mismatch")
    if value.get("status") != "FROZEN_BEFORE_CONTINUATION_ATTEMPTS":
        raise ValueError("continuation release status mismatch")
    if value.get("release_tag") != RELEASE_TAG:
        raise ValueError("continuation release tag mismatch")
    base = read_base_release()
    if value.get("base_filter_inventory_sha256") != base.get("inventory_sha256"):
        raise ValueError("base filter release digest mismatch")
    expected = inventory()
    if value.get("files") != expected:
        raise ValueError("continuation release inventory no longer matches the tree")
    if value.get("inventory_sha256") != inventory_sha256(expected):
        raise ValueError("continuation release inventory digest mismatch")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    release = create_release() if args.write else verify_release()
    if args.write:
        payload = (json.dumps(release, indent=2, sort_keys=True) + "\n").encode()
        RELEASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with RELEASE_PATH.open("xb") as handle:
            handle.write(payload)
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
