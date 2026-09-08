#!/usr/bin/env python3
"""CPU-only validation of isolated working-copy permission normalization."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import traceback
from typing import Any, Sequence


PASS_LABEL = "WORKING_COPY_CPU_GATE_PASS"
FAIL_LABEL = "WORKING_COPY_CPU_GATE_FAIL"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cache_fingerprint(root: Path) -> dict[str, Any]:
    """Reproduce the frozen model-cache observation used by prior gates."""
    digest = hashlib.sha256()
    entry_count = 0
    incomplete: list[str] = []
    for current, directories, files in os.walk(root, followlinks=False):
        directories.sort()
        files.sort()
        for name in [*directories, *files]:
            path = Path(current) / name
            relative = str(path.relative_to(root))
            information = os.lstat(path)
            target = os.readlink(path) if stat.S_ISLNK(information.st_mode) else ""
            row = (
                f"{relative}\0{stat.S_IFMT(information.st_mode)}\0"
                f"{information.st_size}\0{information.st_mtime_ns}\0{target}\0"
            )
            digest.update(row.encode("utf-8", errors="surrogateescape"))
            entry_count += 1
            if name.casefold().endswith((".incomplete", ".partial", ".part", ".tmp")):
                incomplete.append(str(path))
    return {
        "algorithm": "sha256(path,type,lstat_size,mtime_ns,symlink_target)",
        "entry_count": entry_count,
        "incomplete_file_count": len(incomplete),
        "incomplete_files": incomplete,
        "root": str(root),
        "sha256": digest.hexdigest(),
        "timestamp_utc": _utc_now(),
    }


def _run_process(
    arguments: Sequence[str],
    *,
    cwd: Path,
    prefix: Path,
    environment: dict[str, str],
    timeout: int = 600,
) -> subprocess.CompletedProcess[str]:
    values = list(arguments)
    _write_json(prefix.with_suffix(".command.json"), {"argv": values, "cwd": str(cwd)})
    completed = subprocess.run(
        values,
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    prefix.with_suffix(".stdout").write_text(
        completed.stdout or "", encoding="utf-8", newline="\n"
    )
    prefix.with_suffix(".stderr").write_text(
        completed.stderr or "", encoding="utf-8", newline="\n"
    )
    prefix.with_suffix(".exit").write_text(
        f"{completed.returncode}\n", encoding="ascii", newline="\n"
    )
    return completed


def _capture_environment(
    label: str,
    *,
    artifact: Path,
    project: Path,
    vllm_python: Path,
    environment: dict[str, str],
) -> dict[str, str]:
    fingerprint_record = artifact / f"environment-fingerprint-{label}.json"
    fingerprint_inventory = artifact / f"environment-inventory-{label}.json"
    fingerprint = _run_process(
        (
            str(vllm_python),
            str(project / "scripts/environment_fingerprint.py"),
            "capture",
            "--inventory",
            str(fingerprint_inventory),
            "--record",
            str(fingerprint_record),
        ),
        cwd=project,
        prefix=artifact / f"environment-fingerprint-{label}",
        environment=environment,
    )
    if fingerprint.returncode != 0:
        raise RuntimeError(f"environment fingerprint {label} failed")
    content_record = artifact / f"environment-content-digest-{label}.json"
    content_inventory = artifact / f"environment-content-inventory-{label}.json"
    content = _run_process(
        (
            str(vllm_python),
            str(project / "scripts/environment_content_digest.py"),
            "--inventory",
            str(content_inventory),
            "--record",
            str(content_record),
        ),
        cwd=project,
        prefix=artifact / f"environment-content-digest-{label}",
        environment=environment,
    )
    if content.returncode != 0:
        raise RuntimeError(f"environment content digest {label} failed")
    fingerprint_value = json.loads(fingerprint_record.read_text(encoding="utf-8"))
    content_value = json.loads(content_record.read_text(encoding="utf-8"))
    return {
        "content_digest": content_value["canonical_inventory_sha256"],
        "fingerprint": fingerprint_value["canonical_inventory_sha256"],
    }


def _snapshot_files(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): _sha256_file(path)
        for path in sorted(
            root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()
        )
        if path.is_file() and not path.is_symlink()
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--cmpilot-python", type=Path, required=True)
    parser.add_argument("--vllm-python", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--source-fixture", type=Path, required=True)
    parser.add_argument("--model-cache-root", type=Path, required=True)
    parser.add_argument("--expected-environment-fingerprint", required=True)
    parser.add_argument("--expected-runtime-content-digest", required=True)
    parser.add_argument("--expected-model-cache-digest", required=True)
    return parser


def _artifact_directory(arguments: argparse.Namespace) -> Path:
    if arguments.artifact_dir is not None:
        return arguments.artifact_dir
    value = os.environ.get("ARTIFACT_DIR")
    if not value:
        raise RuntimeError("ARTIFACT_DIR is required when --artifact-dir is omitted")
    return Path(value)


def _run_gate(arguments: argparse.Namespace) -> dict[str, object]:
    artifact = _artifact_directory(arguments)
    artifact.mkdir(mode=0o700, parents=True, exist_ok=True)
    scratch = artifact / "scratch"
    scratch.mkdir(mode=0o700, exist_ok=False)
    environment = os.environ.copy()
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": "",
            "PYTHONDONTWRITEBYTECODE": "1",
            "TMPDIR": str(scratch),
        }
    )
    project_root = arguments.project_root.resolve(strict=True)
    source_fixture = arguments.source_fixture.resolve(strict=True)
    model_cache_root = arguments.model_cache_root.resolve(strict=True)
    sys.path.insert(0, str(project_root / "src"))
    from cmpilot.repository_manager import (
        prepare_working_copy,
        repository_content_digest,
        repository_mode_inventory,
        repository_preparation_record,
        run_tests,
    )

    destination = artifact / "temporary-working-copy"
    initial_environment = _capture_environment(
        "initial",
        artifact=artifact,
        project=project_root,
        vllm_python=arguments.vllm_python,
        environment=environment,
    )
    initial_cache = _cache_fingerprint(model_cache_root)
    _write_json(artifact / "model-cache-digest-initial.json", initial_cache)

    source_digest_before = repository_content_digest(source_fixture)
    source_modes_before = repository_mode_inventory(source_fixture)
    source_files_before = _snapshot_files(source_fixture)
    (artifact / "source-content-inventory.json").write_bytes(
        source_digest_before.canonical_inventory
    )
    _write_json(
        artifact / "source-content-digest.json", source_digest_before.as_record()
    )
    _write_json(artifact / "source-mode-inventory.json", source_modes_before)

    working_copy, initial_commit = prepare_working_copy(
        source_fixture,
        destination=destination,
    )
    preparation = repository_preparation_record(
        source_fixture, working_copy, initial_commit
    )
    destination_digest = repository_content_digest(working_copy)
    _write_json(artifact / "repository-preparation.json", preparation)
    _write_json(
        artifact / "destination-content-digest-before-edit.json",
        destination_digest.as_record(),
    )
    (artifact / "destination-content-inventory-before-edit.json").write_bytes(
        destination_digest.canonical_inventory
    )
    _write_json(
        artifact / "destination-mode-inventory.json",
        repository_mode_inventory(working_copy),
    )
    git_status = subprocess.run(
        ["git", "-C", str(working_copy), "status", "--short"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    git_evidence = {
        "directory_created": (working_copy / ".git").is_dir(),
        "initial_commit": initial_commit,
        "status": git_status,
    }
    _write_json(artifact / "git-initialization-evidence.json", git_evidence)

    initial_tests = run_tests(working_copy)
    (artifact / "initial-calculator-tests.stdout").write_text(
        initial_tests.stdout or "", encoding="utf-8", newline="\n"
    )
    (artifact / "initial-calculator-tests.stderr").write_text(
        initial_tests.stderr or "", encoding="utf-8", newline="\n"
    )
    (artifact / "initial-calculator-tests.exit").write_text(
        f"{initial_tests.returncode}\n", encoding="ascii", newline="\n"
    )
    test_output = (initial_tests.stdout or "") + (initial_tests.stderr or "")
    failing_tests = sorted(
        set(re.findall(r"test_calculator\.py::(test_[A-Za-z0-9_]+)", test_output))
    )
    initial_test_record = {
        "exit_code": initial_tests.returncode,
        "failing_tests": failing_tests,
        "three_failures": "3 failed" in test_output,
    }
    _write_json(artifact / "initial-calculator-test-result.json", initial_test_record)

    calculator = working_copy / "calculator.py"
    calculator_before = _sha256_file(calculator)
    with calculator.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write("\n# working-copy permission validation\n")
    calculator_after = _sha256_file(calculator)
    status_after_edit = subprocess.run(
        ["git", "-C", str(working_copy), "status", "--short"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    edit_evidence = {
        "destination_changed": calculator_before != calculator_after,
        "file": "calculator.py",
        "git_status": status_after_edit,
        "sha256_after": calculator_after,
        "sha256_before": calculator_before,
    }
    _write_json(artifact / "temporary-destination-edit.json", edit_evidence)

    source_digest_after = repository_content_digest(source_fixture)
    source_modes_after = repository_mode_inventory(source_fixture)
    source_files_after = _snapshot_files(source_fixture)
    source_integrity = {
        "bytes_unchanged": source_files_before == source_files_after,
        "content_digest_unchanged": source_digest_before == source_digest_after,
        "modes_unchanged": source_modes_before == source_modes_after,
    }
    _write_json(artifact / "source-integrity.json", source_integrity)

    shutil.rmtree(working_copy)
    destination_removed = not destination.exists()
    _write_json(
        artifact / "destination-cleanup.json",
        {"destination": str(destination), "removed": destination_removed},
    )

    targeted = _run_process(
        (
            str(arguments.cmpilot_python),
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/test_working_copy_cpu_job.py",
            "tests/test_repository_copy_permissions.py",
            "tests/test_shared_runtime.py",
            "tests/test_batch_script_attestation.py",
            "tests/test_command_authorization.py",
        ),
        cwd=project_root,
        prefix=artifact / "targeted-regression-tests",
        environment=environment,
    )

    final_environment = _capture_environment(
        "final",
        artifact=artifact,
        project=project_root,
        vllm_python=arguments.vllm_python,
        environment=environment,
    )
    final_cache = _cache_fingerprint(model_cache_root)
    _write_json(artifact / "model-cache-digest-final.json", final_cache)
    integrity = {
        "environment_fingerprint_expected": (
            initial_environment["fingerprint"]
            == final_environment["fingerprint"]
            == arguments.expected_environment_fingerprint
        ),
        "model_cache_expected": (
            initial_cache["sha256"]
            == final_cache["sha256"]
            == arguments.expected_model_cache_digest
        ),
        "runtime_content_expected": (
            initial_environment["content_digest"]
            == final_environment["content_digest"]
            == arguments.expected_runtime_content_digest
        ),
    }
    _write_json(artifact / "environment-and-cache-integrity.json", integrity)

    checks = {
        "content_digest_match": preparation["content_digest_match"] is True,
        "destination_owner_writable": preparation["destination"]["root_mode"]
        == "0700",
        "destination_removed": destination_removed,
        "git_init": git_evidence["directory_created"] and git_status == "",
        "initial_three_failures": initial_tests.returncode == 1
        and "3 failed" in test_output,
        "source_fixture_read_only": preparation["source"]["root_mode"] == "0555",
        "source_integrity": all(source_integrity.values()),
        "targeted_regressions": targeted.returncode == 0,
        "temporary_edit": edit_evidence["destination_changed"],
        **integrity,
    }
    passed = all(checks.values())
    return {
        "checks": checks,
        "destination_content_digest": destination_digest.as_record(),
        "initial_calculator_failures": failing_tests,
        "label": PASS_LABEL if passed else FAIL_LABEL,
        "pass": passed,
        "policy": preparation["policy"],
        "schema": "working-copy-permission-cpu-gate-v2",
        "source_content_digest": source_digest_before.as_record(),
        "timestamp_utc": _utc_now(),
    }


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    artifact = _artifact_directory(arguments)
    try:
        result = _run_gate(arguments)
        classification = {
            "dimensions": {
                "environment_integrity": "PASS"
                if all(
                    result["checks"][key]
                    for key in (
                        "environment_fingerprint_expected",
                        "model_cache_expected",
                        "runtime_content_expected",
                    )
                )
                else "FAIL",
                "git_initialization": "PASS"
                if result["checks"]["git_init"]
                else "FAIL",
                "source_integrity": "PASS"
                if result["checks"]["source_integrity"]
                else "FAIL",
                "working_copy_permissions": "PASS"
                if result["checks"]["destination_owner_writable"]
                else "FAIL",
            },
            "label": result["label"],
        }
        status = 0 if result["pass"] else 1
    except Exception as error:
        artifact.mkdir(mode=0o700, parents=True, exist_ok=True)
        (artifact / "driver-exception.txt").write_text(
            traceback.format_exc(), encoding="utf-8", newline="\n"
        )
        result = {
            "error": f"{type(error).__name__}: {error}",
            "label": FAIL_LABEL,
            "pass": False,
            "schema": "working-copy-permission-cpu-gate-v2",
            "timestamp_utc": _utc_now(),
        }
        classification = {"label": FAIL_LABEL, "reason": result["error"]}
        status = 1
    _write_json(artifact / "result.json", result)
    _write_json(artifact / "classification.json", classification)
    print(result["label"], file=sys.stdout if status == 0 else sys.stderr)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
