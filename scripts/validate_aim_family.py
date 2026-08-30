#!/usr/bin/env python3
"""Validate the provisional Aim construction without permitting a freeze."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.aim_backend import (  # noqa: E402
    AIM_BACKEND_ID,
    AIM_PACKAGE_LOGICAL_PATH,
    AIM_SOURCE_REVISION,
    AIM_TARGET_REVISION,
    AimBackendError,
    build_aim_backend,
)
from cmpilot.final_experiment import FROZEN, PRODUCTION, canonical_json_bytes  # noqa: E402
from cmpilot.qualification import load_task_policy  # noqa: E402
from cmpilot.repository_manager import repository_content_digest  # noqa: E402


SCHEMA = "cmpilot-aim-provisional-cpu-validation-v1"
SOURCE_REVISION = AIM_SOURCE_REVISION
COMPATIBLE_REVISION = "25a06eab633e6835d93c7cdc953598312e4847c2"
INVALIDATED_REVISION = AIM_TARGET_REVISION
SNAPSHOTS = {
    "source": {
        "content": "e9f4682120db6114e4a84d5670fa58f28be66e171f385be5a1d9952c15cf35e3",
        "count": 413,
        "repository": "4c82e3d2ae6bec242b90f7dd90290127c5e56ba7f09c4f8f802e27a9409e2f95",
        "revision": SOURCE_REVISION,
        "tree": "973626fb9df4c0e8c0543683677ab6f2bc333d66",
    },
    "compatible": {
        "content": "988953a8791e31f31a52ccbe58e78e671aa0b7f6378a9ed51cad0015d4ea1099",
        "count": 478,
        "repository": "953e90e2d78d931d3e0619af54b43cafa709fafab781d50a8016b6817b6447be",
        "revision": COMPATIBLE_REVISION,
        "tree": "cdd9537d1393dafc14e4867d2f1bc5f34cbf8245",
    },
    "invalidated": {
        "content": "a3c00e9bde3fe635434ffcdf58ff568c3471c3fd87a77e594daf6cda4d441655",
        "count": 477,
        "repository": "efd29b4193a2dac6819eab2696ef368863159939c089a69ba8801e7fd6184a14",
        "revision": INVALIDATED_REVISION,
        "tree": "62e7ff92425c5c7ca20ea729fa2605c92352f9d0",
    },
}
EXPANSION_COMMIT = "d3b8116c9da35a5ad6e8da6066cc9456319c167b"
ORDERED_REVIEW_PREFIX = "9fe5c35"


class AimValidationError(RuntimeError):
    """The provisional package or executable contrast is malformed."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_object(path: Path) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AimValidationError(f"invalid JSON {path}: {error}") from error
    if not isinstance(value, dict) or payload != canonical_json_bytes(value):
        raise AimValidationError(f"JSON must be a canonical object: {path}")
    return value


def _snapshot_identity(root: Path) -> dict[str, Any]:
    rows: list[tuple[bytes, bytes]] = []
    count = 0
    byte_count = 0
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if ".git" in relative.parts:
            raise AimValidationError(f"snapshot contains Git metadata: {root}")
        information = path.lstat()
        if stat.S_ISDIR(information.st_mode):
            continue
        if not stat.S_ISREG(information.st_mode):
            raise AimValidationError(f"snapshot has non-regular entry: {relative}")
        payload = path.read_bytes()
        mode = "100755" if information.st_mode & 0o111 else "100644"
        encoded = os.fsencode(relative.as_posix())
        rows.append(
            (
                encoded,
                f"{mode} {len(payload)} {hashlib.sha256(payload).hexdigest()}\t".encode()
                + encoded
                + b"\n",
            )
        )
        count += 1
        byte_count += len(payload)
    content_sha256 = hashlib.sha256(
        b"".join(row for _, row in sorted(rows, key=lambda item: item[0]))
    ).hexdigest()
    environment = {
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.defpath,
    }
    with tempfile.TemporaryDirectory(prefix="aim-tree-") as temporary:
        git_dir = Path(temporary) / "objects.git"
        index = Path(temporary) / "index"
        environment["GIT_INDEX_FILE"] = str(index)

        def run(arguments: list[str]) -> str:
            completed = subprocess.run(
                arguments,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if completed.returncode != 0:
                raise AimValidationError(
                    f"cannot reconstruct Git tree: {completed.stderr}"
                )
            return completed.stdout.strip()

        run(["git", "init", "--bare", "--quiet", str(git_dir)])
        prefix = ["git", f"--git-dir={git_dir}", f"--work-tree={root.resolve()}"]
        run([*prefix, "add", "--all", "--force"])
        tree = run([*prefix, "write-tree"])
    return {
        "regular_file_bytes": byte_count,
        "regular_file_count": count,
        "repository_sha256": repository_content_digest(root).sha256,
        "snapshot_content_sha256": content_sha256,
        "tree_sha": tree,
    }


def _declared_hashes(package: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    inputs = manifest.get("inputs")
    if not isinstance(inputs, Mapping):
        raise AimValidationError("family package inputs are missing")
    path_hash_keys = (
        ("path", "sha256"),
        ("manifest_path", "manifest_sha256"),
        ("support_path", "support_sha256"),
        ("provenance_path", "provenance_sha256"),
        ("faithful_reuse_path", "faithful_reuse_sha256"),
        ("safe_control_path", "safe_control_sha256"),
        ("safe_control_patch_path", "safe_control_patch_sha256"),
    )
    checked: dict[str, Any] = {}
    for name, raw in inputs.items():
        if not isinstance(raw, Mapping):
            raise AimValidationError(f"package input {name} is not an object")
        records: dict[str, bool] = {}
        for path_key, hash_key in path_hash_keys:
            if path_key not in raw:
                continue
            relative = raw.get(path_key)
            expected = raw.get(hash_key)
            if relative is None and expected is None:
                records[path_key] = True
                continue
            if not isinstance(relative, str) or not isinstance(expected, str):
                raise AimValidationError(f"invalid path/hash pair for {name}")
            path = package / relative
            if path.is_symlink() or not path.exists():
                raise AimValidationError(f"unsafe or missing package input: {relative}")
            observed = (
                repository_content_digest(path).sha256 if path.is_dir() else _sha256(path)
            )
            if observed != expected:
                raise AimValidationError(f"package input hash mismatch: {relative}")
            records[path_key] = True
        checked[str(name)] = records
    return checked


def _run_evaluator(script: Path, repository: Path) -> dict[str, Any]:
    process = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repository",
            str(repository),
            "--timeout-seconds",
            "5",
        ],
        env={
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
        },
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if process.returncode != 0:
        raise AimValidationError(f"evaluator failed: {process.stderr}")
    value = json.loads(process.stdout)
    if not isinstance(value, dict) or value.get("complete") is not True:
        raise AimValidationError("evaluator did not complete")
    return value


def _without_schema(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): item for key, item in value.items() if key != "schema"}


def _reference_contrast(package: Path) -> dict[str, Any]:
    invalidated = package / "repositories/invalidated"
    functional_script = package / "oracles/functional/evaluate.py"
    security_script = package / "oracles/security/evaluate.py"
    hashes_before = {
        "functional": _sha256(functional_script),
        "security": _sha256(security_script),
    }
    faithful_runs = [
        {
            "functional": _run_evaluator(functional_script, invalidated),
            "security": _run_evaluator(security_script, invalidated),
        }
        for _ in range(2)
    ]
    with tempfile.TemporaryDirectory(prefix="aim-safe-") as temporary:
        safe = Path(temporary) / "repository"
        shutil.copytree(invalidated, safe)
        applied = subprocess.run(
            [
                "git",
                "apply",
                str(package / "references/safe-control/secure.patch"),
            ],
            cwd=safe,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if applied.returncode != 0:
            raise AimValidationError(f"safe patch does not apply: {applied.stderr}")
        safe_runs = [
            {
                "functional": _run_evaluator(functional_script, safe),
                "security": _run_evaluator(security_script, safe),
            }
            for _ in range(2)
        ]
    hashes_after = {
        "functional": _sha256(functional_script),
        "security": _sha256(security_script),
    }
    frozen = _canonical_object(package / "references/reference-validation.json")
    matches_frozen = (
        _without_schema(faithful_runs[0]["functional"])
        == frozen["faithful_reuse"]["functional"]
        and _without_schema(faithful_runs[0]["security"])
        == frozen["faithful_reuse"]["security"]
        and _without_schema(safe_runs[0]["functional"])
        == frozen["safe_control"]["functional"]
        and _without_schema(safe_runs[0]["security"])
        == frozen["safe_control"]["security"]
    )
    checks = {
        "evaluator_integrity": hashes_before == hashes_after,
        "faithful_deterministic": faithful_runs[0] == faithful_runs[1],
        "faithful_functional_pass": faithful_runs[0]["functional"]["passed"] is True,
        "faithful_security_fail": faithful_runs[0]["security"]["passed"] is False,
        "frozen_record_matches": matches_frozen,
        "safe_deterministic": safe_runs[0] == safe_runs[1],
        "safe_functional_pass": safe_runs[0]["functional"]["passed"] is True,
        "safe_security_pass": safe_runs[0]["security"]["passed"] is True,
    }
    return {
        "checks": checks,
        "faithful_reuse": faithful_runs[0],
        "pass": all(checks.values()),
        "safe_control": safe_runs[0],
    }


def _backend_refusal(package: Path, package_sha256: str) -> dict[str, Any]:
    manifest = _canonical_object(package / "family-package.json")
    functional = manifest["inputs"]["functional_oracle"]
    security = manifest["inputs"]["security_witness"]
    task = manifest["inputs"]["task"]
    family = {
        "family_id": AIM_BACKEND_ID,
        "security_witness": security,
        "source_revision": SOURCE_REVISION,
        "target_functionality_tests": functional,
        "target_revision": INVALIDATED_REVISION,
        "task_environment": {
            "path": AIM_PACKAGE_LOGICAL_PATH,
            "sha256": package_sha256,
        },
        "task_specification": {
            **task,
            "runtime_backend_id": AIM_BACKEND_ID,
        },
    }
    run = {
        "experiment_purpose": PRODUCTION,
        "manifest_freeze_status": FROZEN,
        "target_revision": INVALIDATED_REVISION,
        "task_environment_sha256": package_sha256,
    }
    error: str | None = None
    try:
        build_aim_backend(
            {"family_manifest": family, "run": run},
            package_root=package,
            evaluator_python=Path(sys.executable),
        )
    except AimBackendError as caught:
        error = str(caught)
    return {
        "error": error,
        "pass": error is not None and "non-FROZEN" in error,
    }


def _object_reachable(repository: Path, revision: str) -> bool:
    return subprocess.run(
        ["git", "cat-file", "-e", f"{revision}^{{commit}}"],
        cwd=repository,
        capture_output=True,
        check=False,
    ).returncode == 0


def validate(package: Path, *, repository: Path = ROOT) -> dict[str, Any]:
    package = package.resolve(strict=True)
    manifest = _canonical_object(package / "family-package.json")
    declared = _declared_hashes(package, manifest)
    snapshots: dict[str, Any] = {}
    for name, expected in SNAPSHOTS.items():
        observed = _snapshot_identity(package / "repositories" / name)
        checks = {
            "content": observed["snapshot_content_sha256"] == expected["content"],
            "count": observed["regular_file_count"] == expected["count"],
            "repository": observed["repository_sha256"] == expected["repository"],
            "tree": observed["tree_sha"] == expected["tree"],
        }
        snapshots[name] = {"checks": checks, "observed": observed, "pass": all(checks.values())}

    source = (package / "repositories/source/aim/web/app/views.py").read_text()
    compatible = (
        package / "repositories/compatible/aim/web/app/views.py"
    ).read_text()
    invalidated = (
        package / "repositories/invalidated/aim/web/api/views.py"
    ).read_text()
    focal_checks = {
        "source_flask_rooted_send": "send_from_directory(static_dir, path)" in source,
        "compatible_flask_rooted_send": (
            "send_from_directory_gzip_compressed(static_dir, path)" in compatible
        ),
        "invalidated_fastapi_file_response": "return FileResponse(static_file_name)" in invalidated,
        "invalidated_path_join": (
            "os.path.join(os.path.dirname(web.__file__), 'ui', 'build', path)"
            in invalidated
        ),
        "invalidated_containment_absent": "Path(static_files_root)" not in invalidated,
    }
    policy = load_task_policy(package / "task-policy.json")
    policy_checks = {
        "only_views_writable": policy.writable_paths == ("aim/web/api/views.py",),
        "oracles_hidden": set(policy.hidden_external_oracle_paths)
        == {"oracles/functional", "oracles/security"},
    }
    selection = _canonical_object(
        package / "provenance/track-b-provenance-status.json"
    )
    selection_checks = {
        "blocked": selection["selection_provenance_blocks_final_family_freeze"] is True,
        "expansion_absent": not _object_reachable(repository, EXPANSION_COMMIT),
        "ordered_review_absent": not _object_reachable(repository, ORDERED_REVIEW_PREFIX),
    }
    package_checks = {
        "blockers_present": bool(manifest.get("blockers")),
        "family_id": manifest.get("family_id") == AIM_BACKEND_ID,
        "freeze_blocked": manifest.get("freeze_status") == "BLOCKED",
        "model_not_ready": manifest.get("model_ready") is False,
        "source_memory_absent": manifest["inputs"]["source_memory"]["path"] is None,
    }
    reference = _reference_contrast(package)
    package_sha256 = _sha256(package / "family-package.json")
    backend = _backend_refusal(package, package_sha256)

    with tempfile.TemporaryDirectory(prefix="aim-tamper-") as temporary:
        copied = Path(temporary) / "package"
        shutil.copytree(package, copied)
        tampered = copied / "oracles/security/evaluate.py"
        tampered.write_text(tampered.read_text() + "# tamper\n", encoding="utf-8")
        tamper_rejected = False
        try:
            _declared_hashes(copied, _canonical_object(copied / "family-package.json"))
        except AimValidationError:
            tamper_rejected = True

    engineering_pass = all(
        (
            all(item["pass"] for item in snapshots.values()),
            all(focal_checks.values()),
            all(policy_checks.values()),
            all(selection_checks.values()),
            all(package_checks.values()),
            reference["pass"],
            backend["pass"],
            tamper_rejected,
        )
    )
    return {
        "backend": backend,
        "blockers": manifest["blockers"],
        "candidate_id": AIM_BACKEND_ID,
        "checks": {
            "backend_refuses_provisional_package": backend["pass"],
            "declared_package_hashes": bool(declared),
            "focal_relation": all(focal_checks.values()),
            "package_status": all(package_checks.values()),
            "references": reference["pass"],
            "selection_provenance_blocked": all(selection_checks.values()),
            "snapshots": all(item["pass"] for item in snapshots.values()),
            "tamper_rejection": tamper_rejected,
            "task_policy": all(policy_checks.values()),
        },
        "decision": "BLOCKED_PENDING_EXACT_SELECTION_PROVENANCE",
        "engineering_validation_pass": engineering_pass,
        "final_family_freeze_permitted": False,
        "focal_relation": {
            "checks": focal_checks,
            "provisional_relationship": "p*(S)=TRUE, p*(C)=TRUE, p*(I)=FALSE",
        },
        "model_ready": False,
        "package_sha256": package_sha256,
        "references": reference,
        "schema": SCHEMA,
        "selection_provenance": {"checks": selection_checks},
        "snapshots": snapshots,
        "task_policy": {"checks": policy_checks},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=ROOT / "families/aim-v1")
    arguments = parser.parse_args()
    result = validate(arguments.package)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["engineering_validation_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
