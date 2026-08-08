#!/usr/bin/env python3
"""CPU-only gate for the final calculator context/editor/finalization harness."""

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


PASS_LABEL = "CALCULATOR_FINAL_HARNESS_CPU_GATE_PASS"
FAIL_LABEL = "CALCULATOR_FINAL_HARNESS_CPU_GATE_FAIL"
_MANIFEST_EXCLUDES = frozenset(
    {
        "artifact-preservation-idempotency.json",
        "manifest-validation.json",
        "sha256-manifest.txt",
    }
)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _tree_inventory(root: Path, *, ignore_caches: bool = False) -> list[dict[str, Any]]:
    ignored = {".pytest_cache", "__pycache__"} if ignore_caches else set()
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root)
        if any(part in ignored for part in relative.parts):
            continue
        information = path.lstat()
        if stat.S_ISDIR(information.st_mode):
            kind = "directory"
            digest = None
            target = None
        elif stat.S_ISREG(information.st_mode):
            kind = "file"
            digest = _sha256_file(path)
            target = None
        elif stat.S_ISLNK(information.st_mode):
            kind = "symlink"
            digest = None
            target = os.readlink(path)
        else:
            kind = "special"
            digest = None
            target = None
        rows.append(
            {
                "path": relative.as_posix(),
                "type": kind,
                "mode": format(stat.S_IMODE(information.st_mode), "04o"),
                "sha256": digest,
                "target": target,
            }
        )
    return rows


def _scratch_symlink_inventory(root: Path) -> dict[str, Any]:
    """Inventory scratch symlinks without following them or opening their targets."""
    root_resolved = root.resolve(strict=True)
    rows: list[dict[str, Any]] = []
    for current, directories, files in os.walk(
        root, topdown=True, followlinks=False
    ):
        directories.sort()
        files.sort()
        for name in [*directories, *files]:
            path = Path(current) / name
            if not path.is_symlink():
                continue
            try:
                path.resolve(strict=False).relative_to(root_resolved)
                escapes = False
            except (OSError, RuntimeError, ValueError):
                escapes = True
            rows.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "target": os.readlink(path),
                    "escapes_scratch": escapes,
                }
            )
    return {
        "schema": "calculator-final-harness-scratch-symlink-inventory-v1",
        "root": str(root),
        "symlink_count": len(rows),
        "unsafe_symlink_count": sum(row["escapes_scratch"] for row in rows),
        "symlinks": rows,
    }


def _path_metadata(path: Path) -> dict[str, int | str]:
    """Capture target metadata without reading or storing file contents."""
    information = path.stat()
    return {
        "path": str(path),
        "device": information.st_dev,
        "inode": information.st_ino,
        "mode": format(stat.S_IMODE(information.st_mode), "04o"),
        "link_count": information.st_nlink,
        "uid": information.st_uid,
        "gid": information.st_gid,
        "size_bytes": information.st_size,
        "mtime_ns": information.st_mtime_ns,
        "ctime_ns": information.st_ctime_ns,
    }


def _inventory_digest(rows: list[dict[str, Any]]) -> str:
    payload = (
        json.dumps(rows, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _cache_fingerprint(root: Path) -> dict[str, Any]:
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
            digest.update(
                (
                    f"{relative}\0{stat.S_IFMT(information.st_mode)}\0"
                    f"{information.st_size}\0{information.st_mtime_ns}\0{target}\0"
                ).encode("utf-8", errors="surrogateescape")
            )
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
    timeout: int = 1200,
) -> subprocess.CompletedProcess[str]:
    argv = list(arguments)
    _write_json(prefix.with_suffix(".command.json"), {"argv": argv, "cwd": str(cwd)})
    completed = subprocess.run(
        argv,
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


def _remove_scratch_tree(root: Path, *, job_artifact_root: Path) -> None:
    """Remove only the declared job scratch, without following escaping symlinks."""
    expected_root = job_artifact_root / "scratch"
    if (
        not root.is_absolute()
        or not job_artifact_root.is_absolute()
        or root != expected_root
    ):
        raise RuntimeError(
            f"scratch path is not the exact job-owned scratch root: {root}"
        )
    if not root.exists():
        return
    if (
        job_artifact_root.is_symlink()
        or not job_artifact_root.is_dir()
        or root.is_symlink()
        or not root.is_dir()
    ):
        raise RuntimeError(f"scratch path is not a real directory: {root}")

    artifact_resolved = job_artifact_root.resolve(strict=True)
    root_resolved = root.resolve(strict=True)
    if root_resolved.parent != artifact_resolved:
        raise RuntimeError(f"scratch path escapes its job artifact root: {root}")

    def require_contained(path: Path, *, symlink: bool = False) -> None:
        try:
            resolved = path.resolve(strict=not symlink)
            resolved.relative_to(root_resolved)
        except (OSError, RuntimeError, ValueError) as error:
            kind = "symlink" if symlink else "path"
            raise RuntimeError(
                f"scratch {kind} escapes the declared scratch root: {path}"
            ) from error

    # Directory permissions are sufficient for unlinking read-only files. Files
    # are deliberately never chmod'ed, avoiding mode changes through hard links.
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        require_contained(current_path)
        current_path.chmod(0o700)
        for name in directories:
            path = current_path / name
            if path.is_symlink():
                require_contained(path, symlink=True)
            else:
                require_contained(path)
                path.chmod(0o700)
        for name in files:
            path = current_path / name
            if path.is_symlink():
                require_contained(path, symlink=True)
            else:
                require_contained(path)
    shutil.rmtree(root)


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
        "fingerprint": fingerprint_value["canonical_inventory_sha256"],
        "content_digest": content_value["canonical_inventory_sha256"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--cmpilot-python", type=Path, required=True)
    parser.add_argument("--vllm-python", type=Path, required=True)
    parser.add_argument("--mini-python", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--source-fixture", type=Path, required=True)
    parser.add_argument("--oracle-source", type=Path, required=True)
    parser.add_argument("--job-25642-artifacts", type=Path, required=True)
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


def _targeted_tests() -> tuple[str, ...]:
    return (
        "tests/test_context_budget.py",
        "tests/test_calculator_final_harness_evidence.py",
        "tests/test_job_25642_forensics.py",
        "tests/test_job_25642_replay.py",
        "tests/test_calculator_task_policy_prompt.py",
        "tests/test_source_integrity.py",
        "tests/test_protected_path_policy.py",
        "tests/test_external_calculator_oracle.py",
        "tests/test_post_agent_pipeline.py",
        "tests/test_protected_oracle_replay.py",
        "tests/test_protected_path_runtime.py",
        "tests/test_command_authorization.py",
        "tests/test_command_authorization_runtime.py",
        "tests/test_hardened_agent_runtime.py",
        "tests/test_repository_copy_permissions.py",
        "tests/test_action_protocol.py",
        "tests/test_action_protocol_matrix.py",
        "tests/test_working_copy_cpu_job.py",
        "tests/test_batch_script_attestation.py",
        "tests/test_server_command.py",
        "tests/test_shared_runtime.py",
        "tests/test_guided_backend.py",
        "tests/test_environment_fingerprint.py",
        "tests/test_environment_content_digest.py",
        "tests/test_environment_load_gate.py",
        "tests/test_mini_swe_adapter.py",
        "tests/test_mini_swe_config.py",
        "tests/test_openai_transport.py",
        "tests/test_smoke_runner.py",
        "tests/test_calculator_final_harness_cpu_job.py",
        "tests/test_protected_oracle_cpu_job.py",
    )


def _targeted_pytest_command(cmpilot_python: Path) -> tuple[str, ...]:
    return (
        str(cmpilot_python),
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        *_targeted_tests(),
    )


def _run_gate(arguments: argparse.Namespace) -> dict[str, Any]:
    artifact = _artifact_directory(arguments)
    artifact.mkdir(mode=0o700, parents=True, exist_ok=True)
    scratch = artifact / "scratch"
    scratch.mkdir(mode=0o700, exist_ok=False)
    environment = os.environ.copy()
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": "",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "TMPDIR": str(scratch),
            "MINI_SWE_PYTHON": str(arguments.mini_python),
            "CMPILOT_JOB25642_REPLAY_ARTIFACT": str(
                artifact / "deterministic-job-25642-replay.json"
            ),
        }
    )
    project = arguments.project_root.resolve(strict=True)
    source = arguments.source_fixture.resolve(strict=True)
    oracle_source = arguments.oracle_source.resolve(strict=True)
    job_25642 = arguments.job_25642_artifacts.resolve(strict=True)
    model_cache = arguments.model_cache_root.resolve(strict=True)
    sys.path.insert(0, str(project / "src"))
    from cmpilot.external_calculator_oracle import (
        copy_immutable_oracle_bundle,
        validate_oracle_bundle,
    )
    from cmpilot.job_25642_forensics import collect_job_25642_forensics
    from cmpilot.protected_oracle_replay import run_deterministic_job_25575_replay
    from cmpilot.integrations.miniswe.command_authorization import policy_specification
    from cmpilot.task_file_policy import calculator_task_policy

    slurm = {
        "job_id": os.environ.get("SLURM_JOB_ID"),
        "job_name": os.environ.get("SLURM_JOB_NAME"),
        "node": os.environ.get("SLURMD_NODENAME") or os.environ.get("HOSTNAME"),
        "partition": os.environ.get("SLURM_JOB_PARTITION"),
        "nodes": os.environ.get("SLURM_JOB_NUM_NODES"),
        "cpus_per_task": os.environ.get("SLURM_CPUS_PER_TASK"),
        "memory_per_node_mb": os.environ.get("SLURM_MEM_PER_NODE"),
        "job_gpus": os.environ.get("SLURM_JOB_GPUS", ""),
        "cuda_visible_devices": environment["CUDA_VISIBLE_DEVICES"],
    }
    _write_json(artifact / "slurm-resources.json", slurm)
    project_before = _tree_inventory(project, ignore_caches=True)
    historical_before = _tree_inventory(job_25642)
    source_before = _tree_inventory(source)
    environment_initial = _capture_environment(
        "initial",
        artifact=artifact,
        project=project,
        vllm_python=arguments.vllm_python,
        environment=environment,
    )
    cache_initial = _cache_fingerprint(model_cache)
    _write_json(artifact / "model-cache-digest-initial.json", cache_initial)

    policy = calculator_task_policy()
    versioned_policy = json.loads(
        (project / "tasks" / "smoke_test" / "task-policy.json").read_text(
            encoding="utf-8"
        )
    )
    _write_json(
        artifact / "task-policy-verification.json",
        {
            "expected": policy.as_dict(),
            "observed": versioned_policy,
            "pass": versioned_policy == policy.as_dict(),
        },
    )
    _write_json(
        artifact / "protected-path-rule-inventory.json",
        policy_specification(),
    )
    source_modes = {
        "root": format(stat.S_IMODE(source.stat().st_mode), "04o"),
        "calculator.py": format(
            stat.S_IMODE((source / "calculator.py").stat().st_mode), "04o"
        ),
        "test_calculator.py": format(
            stat.S_IMODE((source / "test_calculator.py").stat().st_mode), "04o"
        ),
    }
    _write_json(artifact / "source-fixture-modes.json", source_modes)
    _write_json(
        artifact / "source-fixture-initial.json",
        {
            "content_digest": _inventory_digest(source_before),
            "mode_inventory": source_before,
            "root_mode": source_modes["root"],
        },
    )
    oracle_validation = validate_oracle_bundle(oracle_source)
    _write_json(artifact / "oracle-source-validation.json", oracle_validation)
    immutable_oracle = copy_immutable_oracle_bundle(
        oracle_source, artifact / "immutable-oracle"
    )

    forensic = collect_job_25642_forensics(job_25642)
    _write_json(artifact / "job-25642-forensic-review.json", forensic)
    replay = run_deterministic_job_25575_replay(
        source_repository=source,
        oracle_source=oracle_source,
        output_directory=artifact / "protected-oracle-core-replay",
    )

    evidence = _run_process(
        (
            str(arguments.mini_python),
            str(project / "scripts" / "calculator_final_harness_evidence.py"),
            "--request-fixture",
            str(project / "tests" / "fixtures" / "job_25642_request_15.json"),
            "--tokenizer",
            str(
                Path(
                    "/home/s224049759/model-cache/huggingface/hub/"
                    "models--Qwen--Qwen2.5-Coder-32B-Instruct/snapshots/"
                    "381fc969f78efac66bc87ff7ddeadb7e73c218a7"
                )
            ),
            "--output",
            str(artifact / "calculator-final-harness-evidence.json"),
        ),
        cwd=project,
        prefix=artifact / "calculator-final-harness-evidence",
        environment={**environment, "PYTHONPATH": str(project / "src")},
    )

    external_target = Path("/etc/passwd")
    external_target_before = _path_metadata(external_target)
    _write_json(
        artifact / "external-target-metadata-before.json",
        external_target_before,
    )
    targeted = _run_process(
        _targeted_pytest_command(arguments.cmpilot_python),
        cwd=project,
        prefix=artifact / "targeted-tests",
        environment=environment,
    )
    combined_replay = json.loads(
        (artifact / "deterministic-job-25642-replay.json").read_text(
            encoding="utf-8"
        )
    )
    context_evidence = json.loads(
        (artifact / "calculator-final-harness-evidence.json").read_text(
            encoding="utf-8"
        )
    )
    source_after_tests = _tree_inventory(source)
    _write_json(
        artifact / "source-fixture-final.json",
        {
            "content_digest": _inventory_digest(source_after_tests),
            "mode_inventory": source_after_tests,
            "root_mode": format(stat.S_IMODE(source.stat().st_mode), "04o"),
        },
    )
    _write_json(
        artifact / "source-integrity-input.json",
        {
            "schema": "cmpilot-source-integrity-input-v1",
            "comparisons": [
                {
                    "name": "source-fixture",
                    "initial_path": str(artifact / "source-fixture-initial.json"),
                    "final_path": str(artifact / "source-fixture-final.json"),
                    "expected_root_mode": "0555",
                }
            ],
            "findings": [],
            "metadata": {"job_25642_forensics": "complete"},
        },
    )
    source_integrity_process = _run_process(
        (
            str(arguments.cmpilot_python),
            str(project / "scripts" / "source_integrity.py"),
            "--input",
            str(artifact / "source-integrity-input.json"),
            "--output",
            str(artifact / "source-integrity.json"),
        ),
        cwd=project,
        prefix=artifact / "source-integrity-helper",
        environment={**environment, "PYTHONPATH": str(project / "src")},
    )
    source_integrity = json.loads(
        (artifact / "source-integrity.json").read_text(encoding="utf-8")
    )
    environment_final = _capture_environment(
        "final",
        artifact=artifact,
        project=project,
        vllm_python=arguments.vllm_python,
        environment=environment,
    )
    cache_final = _cache_fingerprint(model_cache)
    _write_json(artifact / "model-cache-digest-final.json", cache_final)
    project_before_cleanup = _tree_inventory(project, ignore_caches=True)
    historical_before_cleanup = _tree_inventory(job_25642)
    source_before_cleanup = _tree_inventory(source)
    scratch_symlinks = _scratch_symlink_inventory(scratch)
    _write_json(
        artifact / "pre-cleanup-scratch-symlink-inventory.json",
        scratch_symlinks,
    )

    _remove_scratch_tree(scratch, job_artifact_root=artifact)

    post_cleanup_environment = environment.copy()
    post_cleanup_environment["TMPDIR"] = str(artifact)
    environment_post_cleanup = _capture_environment(
        "post-cleanup",
        artifact=artifact,
        project=project,
        vllm_python=arguments.vllm_python,
        environment=post_cleanup_environment,
    )
    cache_post_cleanup = _cache_fingerprint(model_cache)
    _write_json(
        artifact / "model-cache-digest-post-cleanup.json", cache_post_cleanup
    )
    project_after_cleanup = _tree_inventory(project, ignore_caches=True)
    historical_after_cleanup = _tree_inventory(job_25642)
    source_after_cleanup = _tree_inventory(source)
    external_target_after = _path_metadata(external_target)
    _write_json(
        artifact / "external-target-metadata-after.json",
        external_target_after,
    )
    external_target_integrity = {
        "path": str(external_target),
        "contents_not_read_or_stored": True,
        "metadata_unchanged": external_target_before == external_target_after,
        "before": external_target_before,
        "after": external_target_after,
    }
    _write_json(
        artifact / "external-target-integrity.json",
        external_target_integrity,
    )
    cleanup_containment = {
        "project_unchanged_before_cleanup": project_before == project_before_cleanup,
        "project_unchanged_after_cleanup": project_before == project_after_cleanup,
        "historical_job_unchanged_before_cleanup": (
            historical_before == historical_before_cleanup
        ),
        "historical_job_unchanged_after_cleanup": (
            historical_before == historical_after_cleanup
        ),
        "source_fixture_unchanged_before_cleanup": (
            source_before == source_before_cleanup
        ),
        "source_fixture_unchanged_after_cleanup": (
            source_before == source_after_cleanup
        ),
        "external_target_unchanged": external_target_integrity[
            "metadata_unchanged"
        ],
        "model_cache_unchanged_after_cleanup": (
            cache_initial["sha256"]
            == cache_final["sha256"]
            == cache_post_cleanup["sha256"]
        ),
    }
    _write_json(
        artifact / "cleanup-containment.json",
        cleanup_containment,
    )
    cleanup = {
        "complete": not scratch.exists(),
        "pre_cleanup_symlink_count": scratch_symlinks["symlink_count"],
        "pre_cleanup_unsafe_symlink_count": scratch_symlinks[
            "unsafe_symlink_count"
        ],
        "escaping_symlinks_followed": 0,
        "external_targets_chmodded": 0,
        "external_paths_deleted": 0,
        "containment": cleanup_containment,
        "gpu_processes_started": 0,
        "model_processes_started": 0,
        "vllm_processes_started": 0,
    }
    _write_json(artifact / "cleanup.json", cleanup)
    _write_json(
        artifact / "post-cleanup-scratch-result.json",
        {
            "scratch_exists": scratch.exists() or scratch.is_symlink(),
            "complete": cleanup["complete"],
        },
    )

    environment_integrity = {
        "environment_fingerprint_expected": (
            environment_initial["fingerprint"]
            == environment_final["fingerprint"]
            == environment_post_cleanup["fingerprint"]
            == arguments.expected_environment_fingerprint
        ),
        "runtime_content_expected": (
            environment_initial["content_digest"]
            == environment_final["content_digest"]
            == environment_post_cleanup["content_digest"]
            == arguments.expected_runtime_content_digest
        ),
        "model_cache_expected": (
            cache_initial["sha256"]
            == cache_final["sha256"]
            == cache_post_cleanup["sha256"]
            == arguments.expected_model_cache_digest
        ),
    }
    _write_json(
        artifact / "environment-model-cache-integrity.json", environment_integrity
    )
    bypass = replay["bypass_simulation"]
    checks = {
        "cpu_only": (
            not slurm["job_gpus"]
            and not slurm["cuda_visible_devices"]
            and slurm["partition"] == "Virtual"
            and slurm["nodes"] == "1"
            and slurm["cpus_per_task"] == "2"
            and slurm["memory_per_node_mb"] == "4096"
        ),
        "source_fixture_read_only": source_modes
        == {
            "root": "0555",
            "calculator.py": "0444",
            "test_calculator.py": "0444",
        },
        "task_policy": versioned_policy == policy.as_dict(),
        "oracle_manifest": oracle_validation["valid"],
        "forensic_review": (
            forensic["artifact_manifest_valid"]
            and forensic["request_context_overflow"]["http_status"] == 400
            and forensic["interactive_editor_bypass"]["shell_execution_count"]
            == 2
            and "unterminated string literal"
            in forensic["source_integrity_generation_failure"]["syntax_error"]
        ),
        "repository_preparation": (
            replay["repository_preparation"]["content_digest_match"]
            and replay["repository_preparation"]["git"]["directory_created"]
            and replay["repository_preparation"]["git"]["status"] == ""
        ),
        "baseline_three_failures": replay["baseline"] == {"failed": 3, "returncode": 1},
        "package_install_shell_calls_zero": combined_replay[
            "package_install_shell_calls"
        ]
        == 0,
        "protected_write_shell_calls_zero": combined_replay[
            "protected_test_write_shell_calls"
        ]
        == 0,
        "nano_shell_calls_zero": combined_replay["nano_shell_calls"] == 0,
        "vim_shell_calls_zero": combined_replay["vim_shell_calls"] == 0,
        "calculator_edit_shell_calls_one": combined_replay[
            "calculator_edit_shell_calls"
        ]
        == 1,
        "visible_protected_test_unchanged": combined_replay[
            "visible_test_unchanged"
        ],
        "immutable_oracle_pass": combined_replay["immutable_oracle_result"]
        == {"failed": 0, "passed": 3},
        "recovery_observations_parser_inert": all(
            count == 0 for count in combined_replay["recovery_parser_matches"]
        ),
        "recovery_observations_propagated": combined_replay[
            "recovery_observations_propagated"
        ]
        == 6,
        "context_evidence_process": evidence.returncode == 0,
        "context_fixture_exact": context_evidence[
            "exact_fixture_prompt_tokens_match"
        ],
        "context_guard_bounded": (
            context_evidence["maximum_emitted_request_tokens"] <= 4096
            and context_evidence["maximum_with_safety_reserve"] <= 4096
        ),
        "context_exhaustion_pretransport": (
            context_evidence["context_exhaustion_http_calls"] == 0
            and not context_evidence["context_exhaustion"]["http_request_sent"]
        ),
        "interactive_editors_pretransport": (
            context_evidence["interactive_editor_shell_calls"] == 0
            and all(
                not decision["authorized"]
                for decision in context_evidence[
                    "interactive_editor_decisions"
                ]
            )
        ),
        "source_integrity_helper": (
            source_integrity_process.returncode == 0 and source_integrity["pass"]
        ),
        "post_agent_analysis_complete": replay["post_agent_analysis_complete"],
        "bypass_detected": bypass["protected_path_integrity_detected"],
        "bypass_technical_failure": bypass["technical_validity"] == "fail",
        "bypass_oracle_still_ran": bypass["external_oracle_ran"],
        "bypass_shutdown_still_ran": bypass["shutdown_ran"],
        "bypass_artifacts_still_complete": bypass["artifact_preservation_ran"],
        "targeted_tests": targeted.returncode == 0,
        "no_unsafe_scratch_symlinks": (
            scratch_symlinks["unsafe_symlink_count"] == 0
        ),
        "project_snapshot_unchanged": (
            project_before == project_after_cleanup
        ),
        "historical_job_unchanged": (
            historical_before == historical_after_cleanup
        ),
        "source_fixture_unchanged": source_before == source_after_cleanup,
        "external_target_unchanged": external_target_integrity[
            "metadata_unchanged"
        ],
        "cleanup_contained": all(cleanup_containment.values()),
        "cleanup_complete": cleanup["complete"],
        **environment_integrity,
    }
    passed = all(checks.values())
    return {
        "schema": "calculator-final-harness-cpu-gate-v1",
        "timestamp_utc": _utc_now(),
        "label": PASS_LABEL if passed else FAIL_LABEL,
        "pass": passed,
        "checks": checks,
        "slurm": slurm,
        "source_fixture_modes": source_modes,
        "task_policy_version": policy.version,
        "oracle_version": oracle_validation["oracle_version"],
        "forensic": forensic,
        "context_evidence": context_evidence,
        "combined_replay_summary": {
            key: combined_replay[key]
            for key in (
                "package_install_shell_calls",
                "nano_shell_calls",
                "vim_shell_calls",
                "protected_test_write_shell_calls",
                "calculator_edit_shell_calls",
                "visible_test_unchanged",
                "immutable_oracle_result",
                "maximum_generated_request_size",
            )
        },
        "core_replay_summary": {
            "baseline": replay["baseline"],
            "post_agent_analysis_complete": replay[
                "post_agent_analysis_complete"
            ],
            "repository_preparation": replay["repository_preparation"],
        },
        "source_integrity": source_integrity,
        "bypass_simulation": bypass,
        "environment_integrity": environment_integrity,
        "scratch_symlink_inventory": scratch_symlinks,
        "external_target_integrity": external_target_integrity,
        "cleanup_containment": cleanup_containment,
        "cleanup": cleanup,
    }


def _manifest_rows(artifact: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for path in sorted(artifact.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(artifact).as_posix()
        if path.name in _MANIFEST_EXCLUDES or path.name.startswith("preservation-pass-"):
            continue
        rows.append((_sha256_file(path), relative))
    return rows


def _preserve(artifact: Path, pass_number: int) -> dict[str, Any]:
    rows = _manifest_rows(artifact)
    text = "".join(f"{digest}  {relative}\n" for digest, relative in rows)
    (artifact / "sha256-manifest.txt").write_text(
        text, encoding="utf-8", newline="\n"
    )
    record = {
        "pass_number": pass_number,
        "entry_count": len(rows),
        "manifest_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "inventory_sha256": _inventory_digest(
            [{"path": relative, "sha256": digest} for digest, relative in rows]
        ),
    }
    _write_json(artifact / f"preservation-pass-{pass_number}.json", record)
    return record


def _validate_manifest(artifact: Path) -> dict[str, Any]:
    manifest = artifact / "sha256-manifest.txt"
    errors: list[str] = []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        path = artifact / relative
        if separator != "  " or not path.is_file():
            errors.append(relative or line)
        elif _sha256_file(path) != digest:
            errors.append(relative)
    self_excluding = "sha256-manifest.txt" not in {
        line.partition("  ")[2]
        for line in manifest.read_text(encoding="utf-8").splitlines()
    }
    return {
        "pass": not errors and self_excluding,
        "error_count": len(errors),
        "errors": errors,
        "manifest_sha256": _sha256_file(manifest),
        "self_excluding": self_excluding,
    }


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    artifact = _artifact_directory(arguments)
    status = 1
    try:
        result = _run_gate(arguments)
        classification = {
            "label": result["label"],
            "dimensions": {
                "model_capability": "not_evaluated_cpu_gate",
                "task_functional_result": "pass"
                if result["checks"]["immutable_oracle_pass"]
                else "fail",
                "technical_validity": "pass" if result["pass"] else "fail",
                "protected_path_violation": False,
                "prohibited_command_executed": False,
                "external_oracle_result": "pass"
                if result["checks"]["immutable_oracle_pass"]
                else "fail",
                "post_agent_analysis_complete": result["checks"][
                    "post_agent_analysis_complete"
                ],
                "cleanup_complete": result["checks"]["cleanup_complete"],
            },
        }
        status = 0 if result["pass"] else 1
    except BaseException as error:
        artifact.mkdir(mode=0o700, parents=True, exist_ok=True)
        (artifact / "driver-exception.txt").write_text(
            traceback.format_exc(), encoding="utf-8", newline="\n"
        )
        scratch = artifact / "scratch"
        cleanup_error: str | None = None
        if scratch.is_dir():
            try:
                _remove_scratch_tree(scratch, job_artifact_root=artifact)
            except BaseException as cleanup_exception:
                cleanup_error = (
                    f"{type(cleanup_exception).__name__}: {cleanup_exception}"
                )
                (artifact / "driver-cleanup-exception.txt").write_text(
                    traceback.format_exc(), encoding="utf-8", newline="\n"
                )
        result = {
            "schema": "calculator-final-harness-cpu-gate-v1",
            "timestamp_utc": _utc_now(),
            "label": FAIL_LABEL,
            "pass": False,
            "error": f"{type(error).__name__}: {error}",
            "cleanup_error": cleanup_error,
        }
        classification = {
            "label": FAIL_LABEL,
            "dimensions": {
                "technical_validity": "fail",
                "cleanup_complete": not scratch.exists(),
            },
        }
    _write_json(artifact / "result.json", result)
    _write_json(artifact / "classification.json", classification)
    first = _preserve(artifact, 1)
    second = _preserve(artifact, 2)
    idempotency = {
        "pass": first["inventory_sha256"] == second["inventory_sha256"],
        "first": first,
        "second": second,
    }
    _write_json(artifact / "artifact-preservation-idempotency.json", idempotency)
    _preserve(artifact, 2)
    validation = _validate_manifest(artifact)
    _write_json(artifact / "manifest-validation.json", validation)
    if not idempotency["pass"] or not validation["pass"]:
        status = 1
    print(PASS_LABEL if status == 0 else FAIL_LABEL)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
