#!/usr/bin/env python3
"""Verify the isolated Devstral candidate environment without importing models."""

from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import platform
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.devstral_profile import (  # noqa: E402
    CANDIDATE_LOCK,
    CANDIDATE_LOCK_SHA256,
    ENVIRONMENT_PATH,
    MODEL_SNAPSHOT,
    REQUIRED_SNAPSHOT_FILES,
    SERVER_PYTHON,
    normalize_package_name,
    validate_candidate_environment,
)


PROFILE_CONFIG = ROOT / "configs/models/devstral-small-2507.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def installed_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name")
        if name:
            versions[normalize_package_name(name)] = distribution.version
    return versions


def verification_result() -> dict[str, object]:
    lock_path = ROOT / CANDIDATE_LOCK
    config = json.loads(PROFILE_CONFIG.read_text(encoding="utf-8"))
    lock_sha256 = sha256_file(lock_path) if lock_path.is_file() else None
    package_errors = validate_candidate_environment(
        python_version=platform.python_version(),
        package_versions=installed_versions(),
    )
    actual_interpreter = Path(sys.executable).resolve()
    actual_prefix = Path(sys.prefix).resolve()
    expected_interpreter = SERVER_PYTHON.resolve(strict=False)
    expected_prefix = ENVIRONMENT_PATH.resolve(strict=False)
    snapshot_files = {
        name: (MODEL_SNAPSHOT / name).is_file() for name in REQUIRED_SNAPSHOT_FILES
    }
    environment_identity_frozen = all(
        config["environment"].get(key) is not None
        for key in (
            "environment_fingerprint_sha256",
            "authoritative_content_digest_sha256",
        )
    )
    snapshot_identity_frozen = config["model"].get("snapshot_file_sha256") is not None
    checks = {
        "candidate_lock_matches": lock_sha256 == CANDIDATE_LOCK_SHA256,
        "exact_environment_prefix": actual_prefix == expected_prefix,
        "exact_server_interpreter": actual_interpreter == expected_interpreter,
        "candidate_python_and_direct_pins_match": not package_errors,
        "environment_identity_frozen": environment_identity_frozen,
        "snapshot_directory_exists": MODEL_SNAPSHOT.is_dir(),
        "snapshot_identity_frozen": snapshot_identity_frozen,
        "snapshot_required_files_exist": all(snapshot_files.values()),
    }
    candidate_environment_matches = all(
        checks[key]
        for key in (
            "candidate_lock_matches",
            "exact_environment_prefix",
            "exact_server_interpreter",
            "candidate_python_and_direct_pins_match",
        )
    )
    production_ready = candidate_environment_matches and all(checks.values())
    return {
        "actual_interpreter": str(actual_interpreter),
        "actual_prefix": str(actual_prefix),
        "candidate_environment_matches": candidate_environment_matches,
        "checks": checks,
        "environment_path": str(ENVIRONMENT_PATH),
        "lock_sha256": lock_sha256,
        "package_errors": list(package_errors),
        "production_ready": production_ready,
        "schema": "devstral-serving-environment-verification-v1",
        "snapshot_files": snapshot_files,
        "status": "READY" if production_ready else "NOT_READY",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = verification_result()
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.parent.resolve(strict=True)
        with arguments.output.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
    sys.stdout.write(payload)
    return 0 if result["production_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
