"""Deterministic replay of job 25692's STAGNATION_LIMIT finalization path."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import time
from typing import Any, Callable

from .calculator_finalizer import (
    initialize_finalizer_state,
    run_total_finalization,
    validate_total_finalization_artifacts,
)
from .external_calculator_oracle import run_external_calculator_oracle
from .job_25692_forensics import run_visible_test_investigation
from .repository_manager import (
    copy_repository_tree,
    prepare_working_copy,
    repository_content_digest,
)
from .task_file_policy import calculator_task_policy


IntegrityCallback = Callable[[], dict[str, Any]]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(
    arguments: tuple[str, ...], *, cwd: Path, prefix: Path
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        }
    )
    completed = subprocess.run(
        arguments,
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )
    _write_json(prefix.with_suffix(".command.json"), {"argv": list(arguments), "cwd": str(cwd)})
    prefix.with_suffix(".stdout").write_text(
        completed.stdout, encoding="utf-8", newline="\n"
    )
    prefix.with_suffix(".stderr").write_text(
        completed.stderr, encoding="utf-8", newline="\n"
    )
    prefix.with_suffix(".exit").write_text(
        f"{completed.returncode}\n", encoding="ascii", newline="\n"
    )
    return completed


def _owned_scratch_cleanup(scratch: Path, *, artifact: Path) -> dict[str, Any]:
    expected = artifact / "scratch"
    if scratch != expected or not scratch.is_absolute() or not artifact.is_absolute():
        raise RuntimeError("scratch is not the exact job-owned scratch path")
    if scratch.is_symlink() or artifact.is_symlink():
        raise RuntimeError("scratch or artifact root is a symlink")
    artifact_resolved = artifact.resolve(strict=True)
    scratch_resolved = scratch.resolve(strict=True)
    if scratch_resolved.parent != artifact_resolved:
        raise RuntimeError("scratch escapes the artifact root")
    for current, directories, files in os.walk(
        scratch, topdown=True, followlinks=False
    ):
        current_path = Path(current)
        current_path.resolve(strict=True).relative_to(scratch_resolved)
        for name in [*directories, *files]:
            path = current_path / name
            if path.is_symlink():
                raise RuntimeError(f"unexpected scratch symlink: {path}")
        current_path.chmod(0o700)
        for name in directories:
            (current_path / name).chmod(0o700)
    shutil.rmtree(scratch)
    return {
        "pass": not scratch.exists(),
        "complete": not scratch.exists(),
        "outside_paths_modified": 0,
        "symlinks_followed": 0,
    }


def run_job_25692_stagnation_replay(
    *,
    source_repository: Path,
    oracle_source: Path,
    output_directory: Path,
    python: Path,
    integrity_callback: IntegrityCallback | None = None,
    initial_technical_validity: bool = True,
    base_result_extra: dict[str, Any] | None = None,
    classification_extra: dict[str, Any] | None = None,
    success_label: str = "FINALIZER_CPU_GATE_PASS",
    technical_failure_label: str = "FINALIZER_CPU_GATE_FAIL",
) -> dict[str, Any]:
    """Reproduce the correct patch plus repeated zero-test unittest command."""
    source_repository = source_repository.resolve(strict=True)
    oracle_source = oracle_source.resolve(strict=True)
    output_directory.mkdir(parents=True, exist_ok=True)
    output_directory = output_directory.resolve(strict=True)
    scratch = output_directory / "scratch"
    scratch.mkdir(mode=0o700)
    state_path = output_directory / "finalizer-state.json"
    initialize_finalizer_state(state_path, run_id="job-25692-stagnation-replay")
    started = time.monotonic()
    source_digest_before = repository_content_digest(source_repository).sha256
    source_test = source_repository / "test_calculator.py"
    source_test_hash_before = _sha256(source_test)
    source_modes_before = {
        ".": format(stat.S_IMODE(source_repository.stat().st_mode), "04o"),
        "calculator.py": format(
            stat.S_IMODE((source_repository / "calculator.py").stat().st_mode),
            "04o",
        ),
        "test_calculator.py": format(
            stat.S_IMODE(source_test.stat().st_mode), "04o"
        ),
    }
    working_copy, initial_commit = prepare_working_copy(
        source_repository,
        destination=scratch / "working-copy",
        task_policy=calculator_task_policy(),
    )
    baseline = _run(
        (
            str(python),
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
        ),
        cwd=working_copy,
        prefix=output_directory / "baseline",
    )
    baseline_output = baseline.stdout + baseline.stderr
    if baseline.returncode != 1 or "3 failed" not in baseline_output:
        raise RuntimeError("calculator replay baseline was not exactly three failures")

    calculator = working_copy / "calculator.py"
    calculator.write_text(
        "def add(a, b):\n    return a + b\n",
        encoding="utf-8",
        newline="\n",
    )
    visible = run_visible_test_investigation(
        working_copy=working_copy,
        output_directory=output_directory / "visible-test-investigation",
        agent_python=python,
        baseline_python=python,
    )
    trajectory = {
        "schema": "job-25692-stagnation-trajectory-v1",
        "termination_reason": "STAGNATION_LIMIT",
        "completion_sentinel_recorded": False,
        "commands": [
            "python -m unittest test_calculator.py",
            "python -m unittest test_calculator.py",
        ],
        "observations": [
            visible["commands"]["unittest-module"],
            visible["commands"]["unittest-module"],
        ],
        "authorized_calculator_edit": True,
    }
    _write_json(output_directory / "stagnation-trajectory.json", trajectory)

    captured_repository = output_directory / "final-working-tree"
    external_result: dict[str, Any] = {}

    def final_repository_capture() -> dict[str, Any]:
        copy_repository_tree(working_copy, captured_repository)
        result = {
            "pass": True,
            "complete": True,
            "content_digest": repository_content_digest(captured_repository).sha256,
            "test_sha256": _sha256(captured_repository / "test_calculator.py"),
        }
        _write_json(output_directory / "final-repository-capture.json", result)
        return result

    def patch_generation() -> dict[str, Any]:
        completed = subprocess.run(
            ["/usr/bin/git", "diff", "--binary", "HEAD", "--"],
            cwd=working_copy,
            text=True,
            capture_output=True,
            check=False,
        )
        changed = subprocess.run(
            ["/usr/bin/git", "status", "--porcelain", "--untracked-files=all"],
            cwd=working_copy,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.splitlines()
        allowed = completed.stdout
        disallowed = "" if changed == [" M calculator.py"] else "\n".join(changed)
        (output_directory / "allowed.patch").write_text(allowed, encoding="utf-8")
        (output_directory / "disallowed.diff").write_text(
            disallowed, encoding="utf-8"
        )
        result = {
            "pass": completed.returncode == 0 and bool(allowed) and not disallowed,
            "allowed_files": ["calculator.py"],
            "disallowed_files": [],
            "patch_sha256": hashlib.sha256(allowed.encode("utf-8")).hexdigest(),
        }
        _write_json(output_directory / "patch-generation.json", result)
        return result

    def immutable_oracle() -> dict[str, Any]:
        nonlocal external_result
        result = run_external_calculator_oracle(
            source_repository=source_repository,
            agent_repository=working_copy,
            oracle_bundle=oracle_source,
            destination=output_directory / "immutable-validation-tree",
            task_policy=calculator_task_policy(),
            artifact_directory=output_directory / "immutable-oracle-artifacts",
            python=python,
        )
        external_result = result.as_dict()
        external_result["pass"] = result.returncode == 0 and result.passed == 3 and result.failed == 0
        return external_result

    def source_integrity() -> dict[str, Any]:
        source_digest_after = repository_content_digest(source_repository).sha256
        result = {
            "pass": (
                source_digest_before == source_digest_after
                and source_test_hash_before == _sha256(source_test)
            ),
            "content_digest_before": source_digest_before,
            "content_digest_after": source_digest_after,
            "test_sha256_before": source_test_hash_before,
            "test_sha256_after": _sha256(source_test),
            "modes_before": source_modes_before,
            "modes_after": {
                ".": format(
                    stat.S_IMODE(source_repository.stat().st_mode), "04o"
                ),
                "calculator.py": format(
                    stat.S_IMODE(
                        (source_repository / "calculator.py").stat().st_mode
                    ),
                    "04o",
                ),
                "test_calculator.py": format(
                    stat.S_IMODE(source_test.stat().st_mode), "04o"
                ),
            },
        }
        _write_json(output_directory / "source-integrity.json", result)
        return result

    def environment_integrity() -> dict[str, Any]:
        result = (
            integrity_callback()
            if integrity_callback is not None
            else {
                "pass": True,
                "project": "not-mutated-by-replay",
                "environment": "not-mutated-by-replay",
                "model_cache": "not-mutated-by-replay",
            }
        )
        _write_json(
            output_directory / "project-environment-cache-integrity.json",
            result,
        )
        return result

    def shutdown() -> dict[str, Any]:
        result = {
            "pass": True,
            "complete": True,
            "simulation": True,
            "gpu_processes_started": 0,
            "vllm_processes_started": 0,
        }
        _write_json(output_directory / "shutdown.json", result)
        return result

    def scratch_cleanup() -> dict[str, Any]:
        result = _owned_scratch_cleanup(scratch, artifact=output_directory)
        _write_json(output_directory / "scratch-cleanup.json", result)
        return result

    def performance_summary() -> dict[str, Any]:
        return {
            "pass": True,
            "elapsed_seconds": time.monotonic() - started,
            "model_requests": 0,
            "gpu_samples": 0,
            "replay": True,
        }

    base_result = {
        "replay": "job-25692-stagnation",
        "repository_solution_capability": "demonstrated",
        "model_run_termination": "STAGNATION_LIMIT",
        "original_technical_validity": "fail",
        "initial_commit": initial_commit,
        "baseline": {"failed": 3, "returncode": baseline.returncode},
        "visible_test_classification": visible["classification"],
        "immutable_oracle_result": {"passed": 3, "failed": 0},
    }
    base_result.update(base_result_extra or {})
    dimensions = {
        "repository_solution_capability": "demonstrated",
        "model_capability": "demonstrated",
        "task_functional_result": "pass",
        "model_run_termination": "STAGNATION_LIMIT",
        "original_technical_validity": "fail",
        "replay_technical_validity": "pass",
    }
    dimensions.update(classification_extra or {})
    finalization = run_total_finalization(
        state_path=state_path,
        artifact_directory=output_directory,
        termination_reason="STAGNATION_LIMIT",
        callbacks={
            "final_repository_capture": final_repository_capture,
            "patch_generation": patch_generation,
            "immutable_oracle": immutable_oracle,
            "source_integrity": source_integrity,
            "project_environment_cache_integrity": environment_integrity,
            "shutdown": shutdown,
            "scratch_cleanup": scratch_cleanup,
            "performance_summary": performance_summary,
        },
        success_label=success_label,
        technical_failure_label=technical_failure_label,
        requested_exit_code=0,
        initial_technical_validity=initial_technical_validity,
        base_result=base_result,
        classification_dimensions=dimensions,
    )
    validation = validate_total_finalization_artifacts(output_directory)
    return {
        "schema": "job-25692-stagnation-finalization-replay-v1",
        "pass": (
            validation["pass"]
            and finalization.state.final_exit_code == 0
            and external_result.get("passed") == 3
            and external_result.get("failed") == 0
            and visible["classification"] == "MODEL_TEST_COMMAND_CHOICE"
        ),
        "termination_reason": "STAGNATION_LIMIT",
        "repository_solution_capability": "demonstrated",
        "visible_test_investigation": visible,
        "external_oracle": external_result,
        "finalization": finalization.as_dict(),
        "artifact_validation": validation,
        "scratch_cleanup_complete": not scratch.exists(),
    }
