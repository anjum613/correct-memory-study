#!/usr/bin/env python3
"""Create or verify the content-addressed controlled-v2 reserve release."""

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
RESERVE_ROOT = REPO_ROOT / "synthetic_triplets/controlled_v2_reserve"
RELEASE_PATH = RESERVE_ROOT / "reserve_release.json"
RELEASE_TAG = "controlled-synthetic-v2-reserve-v1"
BASE_FILTER_RELEASE = REPO_ROOT / "synthetic_triplets/controlled_v2/filter_release.json"
CONTINUATION_RELEASE = (
    REPO_ROOT / "synthetic_triplets/controlled_v2_continuation/continuation_release.json"
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def released_paths() -> list[Path]:
    paths = {
        REPO_ROOT / "scripts/reserve_catalog_v2.py",
        REPO_ROOT / "scripts/freeze_controlled_v2_reserve.py",
        REPO_ROOT / "scripts/materialize_controlled_v2_reserve.py",
        REPO_ROOT / "scripts/run_controlled_v2_reserve.py",
        REPO_ROOT / "scripts/validate_controlled_triplet_v2.py",
        REPO_ROOT / "scripts/validate_controlled_triplet_v2_reserve.py",
        REPO_ROOT / "scripts/verify_controlled_v2_reserve_reference_matrix.py",
        REPO_ROOT / "scripts/check_controlled_v2_public.py",
        REPO_ROOT / "tests/test_reserve_construction_v2.py",
        BASE_FILTER_RELEASE,
        CONTINUATION_RELEASE,
    }
    for path in RESERVE_ROOT.rglob("*"):
        if not path.is_file() or path == RELEASE_PATH:
            continue
        relative = path.relative_to(RESERVE_ROOT)
        if relative.parts and relative.parts[0] in {"acquisitions", "reviews"}:
            continue
        paths.add(path)
    missing = [str(path.relative_to(REPO_ROOT)) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"reserve release inputs missing: {sorted(missing)}")
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


def reserve_attempts_exist() -> bool:
    root = RESERVE_ROOT / "acquisitions"
    return root.exists() and any(path.is_file() for path in root.rglob("*"))


def run_checks() -> list[dict[str, Any]]:
    commands = [
        [sys.executable, "scripts/materialize_controlled_v2_reserve.py", "--check"],
        [sys.executable, "scripts/verify_controlled_v2_reserve_reference_matrix.py", "--compact"],
        [sys.executable, "-m", "pytest", "-q", "tests/test_reserve_construction_v2.py"],
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
        records.append(
            {
                "command": command,
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        )
        if completed.returncode:
            raise RuntimeError(f"reserve pre-freeze check failed: {' '.join(command)}")
    return records


def read_release(path: Path, schema: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != schema:
        raise ValueError(f"release schema mismatch: {path}")
    return value


def create_release() -> dict[str, Any]:
    if RELEASE_PATH.exists():
        raise FileExistsError(f"refusing to overwrite release: {RELEASE_PATH}")
    if reserve_attempts_exist():
        raise RuntimeError("reserve constructor attempts already exist")
    base_release = read_release(
        BASE_FILTER_RELEASE, "controlled-synthetic-v2-filter-release/1"
    )
    continuation_release = read_release(
        CONTINUATION_RELEASE, "controlled-synthetic-v2-continuation-release/1"
    )
    checks = run_checks()
    files = inventory()
    return {
        "schema_version": "controlled-synthetic-v2-reserve-release/1",
        "status": "FROZEN_BEFORE_ANY_RESERVE_CONSTRUCTOR_RUN",
        "scientific_status": "OUTCOME_INFORMED_CONSTRUCTION_REPLACEMENT",
        "frozen_at_utc": utc_now(),
        "release_tag": RELEASE_TAG,
        "base_filter_inventory_sha256": base_release["inventory_sha256"],
        "continuation_inventory_sha256": continuation_release["inventory_sha256"],
        "reserve_order": ["R01", "R02", "R03", "R04", "R05"],
        "reserve_family_count": 5,
        "reserve_attempts_existed_at_release": False,
        "evaluated_agent_runs_existed_at_release": False,
        "files": files,
        "inventory_sha256": inventory_sha256(files),
        "pre_freeze_validation": {"all_passed": True, "checks": checks},
    }


def verify_release() -> dict[str, Any]:
    value = json.loads(RELEASE_PATH.read_text(encoding="utf-8"))
    if value.get("schema_version") != "controlled-synthetic-v2-reserve-release/1":
        raise ValueError("reserve release schema mismatch")
    if value.get("status") != "FROZEN_BEFORE_ANY_RESERVE_CONSTRUCTOR_RUN":
        raise ValueError("reserve release status mismatch")
    if value.get("release_tag") != RELEASE_TAG:
        raise ValueError("reserve release tag mismatch")
    expected = inventory()
    if value.get("files") != expected:
        raise ValueError("reserve release inventory no longer matches the tree")
    if value.get("inventory_sha256") != inventory_sha256(expected):
        raise ValueError("reserve release inventory digest mismatch")
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
                "reserve_family_count": release["reserve_family_count"],
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
