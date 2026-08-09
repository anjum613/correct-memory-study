#!/usr/bin/env python3
"""CPU-only mandatory gate for the frozen Qwen32B no-memory suite."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.integrations.miniswe.command_authorization import (  # noqa: E402
    authorize_command,
)
from cmpilot.qualification import (  # noqa: E402
    CMPILOT_PYTHON,
    FROZEN_HARNESS_COMMIT,
    FROZEN_TAG,
    QualificationError,
    SHARED_ARTIFACT_ROOT,
    artifact_manifest,
    copy_immutable_oracle_bundle,
    load_json,
    load_suite_manifest,
    no_memory_prompt_check,
    prepare_qualification_working_copy,
    render_task_prompts,
    repository_content_digest,
    run_external_oracle,
    sha256_file,
    task_paths,
    task_policy_from_manifest,
    validate_oracle_bundle,
    validate_task_manifest,
    write_canonical_json,
)
from cmpilot.repository_manager import (  # noqa: E402
    git,
    repository_mode_inventory,
)


DEFAULT_OUTPUT = SHARED_ARTIFACT_ROOT / "cpu-preflight"
_TEST_SUMMARY = re.compile(
    r"(?P<passed>\d+) passed(?:, (?P<failed>\d+) failed)?(?:, (?P<skipped>\d+) skipped)?"
)


def _run(
    argv: Sequence[str], *, cwd: Path, prefix: Path, timeout: int = 1800
) -> dict[str, Any]:
    completed = subprocess.run(
        list(argv),
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
        env={
            **os.environ,
            "CUDA_VISIBLE_DEVICES": "",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        },
    )
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_suffix(".stdout").write_text(completed.stdout or "", encoding="utf-8")
    prefix.with_suffix(".stderr").write_text(completed.stderr or "", encoding="utf-8")
    prefix.with_suffix(".exit").write_text(f"{completed.returncode}\n", encoding="ascii")
    output = (completed.stdout or "") + (completed.stderr or "")
    match = _TEST_SUMMARY.search(output)
    record = {
        "argv": list(argv),
        "cwd": str(cwd),
        "exit_code": completed.returncode,
        "failed": int(match.group("failed") or 0) if match else None,
        "passed": int(match.group("passed")) if match else None,
        "skipped": int(match.group("skipped") or 0) if match else None,
        "stderr": str(prefix.with_suffix(".stderr")),
        "stdout": str(prefix.with_suffix(".stdout")),
    }
    write_canonical_json(prefix.with_suffix(".json"), record)
    return record


def _task_gate(
    project: Path,
    task: dict[str, Any],
    output: Path,
) -> dict[str, Any]:
    task_id = task["task_id"]
    task_output = output / "tasks" / task_id
    task_output.mkdir(parents=True)
    errors = validate_task_manifest(project, task)
    paths = task_paths(project, task)
    policy = task_policy_from_manifest(project, task)
    oracle_expected = task["immutable_external_oracle"]["manifest_sha256"]
    oracle_before = validate_oracle_bundle(
        paths["oracle"], expected_manifest_sha256=oracle_expected
    )
    hashes = {
        "oracle_bundle": {
            "actual": oracle_before["bundle_sha256"],
            "expected": task["immutable_external_oracle"]["bundle_sha256"],
        },
        "oracle_config": {
            "actual": sha256_file(paths["oracle"] / "oracle.json"),
            "expected": task["immutable_external_oracle"]["oracle_config_sha256"],
        },
        "oracle_manifest": {
            "actual": sha256_file(paths["oracle"] / "manifest.json"),
            "expected": oracle_expected,
        },
        "oracle_test": {
            "actual": sha256_file(paths["oracle"] / "test_oracle.py"),
            "expected": task["immutable_external_oracle"]["oracle_test_sha256"],
        },
        "reference_patch": {
            "actual": sha256_file(paths["reference_patch"]),
            "expected": task["reference_patch"]["sha256"],
        },
        "source": {
            "actual": repository_content_digest(paths["repository"]).sha256,
            "expected": task["repository"]["source_sha256"],
        },
        "task_instruction": {
            "actual": sha256_file(paths["task_instruction"]),
            "expected": task["task_instruction"]["sha256"],
        },
        "task_policy": {
            "actual": sha256_file(paths["task_policy"]),
            "expected": task["task_policy"]["sha256"],
        },
    }
    source_hashes_pass = all(row["actual"] == row["expected"] for row in hashes.values())

    clean, clean_commit = prepare_qualification_working_copy(
        paths["repository"],
        destination=task_output / "clean-working-copy",
        task_policy=policy,
    )
    immutable = copy_immutable_oracle_bundle(
        paths["oracle"],
        task_output / "immutable-oracle",
        expected_manifest_sha256=oracle_expected,
    )
    clean_result = run_external_oracle(
        source_repository=paths["repository"],
        agent_repository=clean,
        oracle_bundle=immutable,
        expected_manifest_sha256=oracle_expected,
        destination=task_output / "clean-validation-tree",
        policy=policy,
        artifact_directory=task_output / "clean-oracle-artifacts",
    )
    clean_expected = task["expected_clean_state_oracle_result"]
    clean_failure_pass = (
        clean_result.returncode == clean_expected["returncode"]
        and clean_result.passed == clean_expected["passed"]
        and clean_result.failed == clean_expected["failed"]
        and clean_result.returncode != 0
    )

    reference, reference_commit = prepare_qualification_working_copy(
        paths["repository"],
        destination=task_output / "reference-working-copy",
        task_policy=policy,
    )
    applied = _run(
        ("git", "apply", "--whitespace=error", str(paths["reference_patch"])),
        cwd=reference,
        prefix=task_output / "reference-patch",
    )
    reference_result = run_external_oracle(
        source_repository=paths["repository"],
        agent_repository=reference,
        oracle_bundle=immutable,
        expected_manifest_sha256=oracle_expected,
        destination=task_output / "reference-validation-tree",
        policy=policy,
        artifact_directory=task_output / "reference-oracle-artifacts",
    )
    expected_reference = task["expected_reference_patch_oracle_result"]
    reference_pass = (
        applied["exit_code"] == 0
        and reference_result.returncode == expected_reference["returncode"] == 0
        and reference_result.passed == expected_reference["passed"]
        and reference_result.failed == expected_reference["failed"] == 0
        and not reference_result.disallowed_diff
    )

    reset, reset_commit = prepare_qualification_working_copy(
        paths["repository"],
        destination=task_output / "reset-working-copy",
        task_policy=policy,
    )
    deterministic_reset = (
        clean_commit == reference_commit == reset_commit
        and repository_content_digest(clean).sha256
        == repository_content_digest(reset).sha256
        == task["repository"]["source_sha256"]
    )
    mode_rows = repository_mode_inventory(clean)
    mode_by_path = {row["path"]: row["mode"] for row in mode_rows}
    permissions = all(
        mode_by_path[path] in {"0600", "0700"} for path in policy.writable_paths
    ) and all(
        mode_by_path[path] in {"0400", "0500"}
        for path in policy.readable_protected_paths
    )
    writable_command = f"echo x > {policy.writable_paths[0]}"
    protected_command = f"echo x > {policy.readable_protected_paths[0]}"
    writable_decision = authorize_command(writable_command, task_policy=policy)
    protected_decision = authorize_command(protected_command, task_policy=policy)
    enforcement = writable_decision.authorized and not protected_decision.authorized

    prompts = render_task_prompts(
        paths["task_instruction"].read_text(encoding="utf-8"), policy
    )
    memory = no_memory_prompt_check(prompts)
    fixture_files = {
        path.relative_to(paths["repository"]).as_posix()
        for path in paths["repository"].rglob("*")
        if path.is_file()
    }
    oracle_isolation = (
        "test_oracle.py" not in fixture_files
        and not paths["oracle"].is_relative_to(clean)
        and oracle_before["manifest_sha256"]
        == validate_oracle_bundle(
            paths["oracle"], expected_manifest_sha256=oracle_expected
        )["manifest_sha256"]
    )
    text_to_scan = (
        paths["task_instruction"].read_text(encoding="utf-8")
        + paths["task_policy"].read_text(encoding="utf-8")
        + "\n".join(
            path.read_text(encoding="utf-8")
            for path in paths["repository"].rglob("*.py")
        )
    ).casefold()
    package_or_network_free = not any(
        marker in text_to_scan
        for marker in (
            "pip install",
            "conda install",
            "http://",
            "https://",
            "requests.get",
            "urllib.request",
        )
    )
    artifact_path_pass = (
        Path(task["artifact_destination"]).is_absolute()
        and Path(task["artifact_destination"]).is_relative_to(SHARED_ARTIFACT_ROOT)
    )
    checks = {
        "artifact_path": artifact_path_pass,
        "canonical_prompt_rendering": prompts["parser_match_counts"]
        == {"system": 1, "task": 0},
        "clean_repository_preparation": clean_commit == reset_commit,
        "deterministic_reset": deterministic_reset,
        "immutable_oracle_isolation": oracle_isolation,
        "no_memory_or_residual_state": memory["pass"]
        and memory["residual_messages"] == 0,
        "no_package_or_network_requirement": package_or_network_free,
        "reference_patch_passes_oracle": reference_pass,
        "source_oracle_reference_hashes": source_hashes_pass,
        "unpatched_oracle_fails": clean_failure_pass,
        "writable_protected_enforcement": permissions and enforcement,
    }
    record = {
        "checks": checks,
        "errors": errors,
        "hashes": hashes,
        "oracle": {
            "clean": clean_result.as_dict(),
            "reference": reference_result.as_dict(),
        },
        "pass": not errors and all(checks.values()),
        "policy_decisions": {
            "protected": protected_decision.as_dict(),
            "writable": writable_decision.as_dict(),
        },
        "prompt_rendering": prompts,
        "task_id": task_id,
    }
    write_canonical_json(task_output / "task-preflight-result.json", record)
    return record


def _verify_freeze(project: Path, suite: dict[str, Any]) -> dict[str, Any]:
    freeze_path = project / suite["freeze_manifest"]["path"]
    freeze_sha = sha256_file(freeze_path)
    freeze = load_json(freeze_path)
    components = []
    for record in freeze["components"]:
        source = Path(record["source_path"])
        if not source.is_absolute():
            source = project / source
        actual = sha256_file(source)
        components.append(
            {
                "actual_sha256": actual,
                "component_name": record["component_name"],
                "expected_sha256": record["sha256"],
                "pass": actual == record["sha256"],
                "source_path": str(source),
            }
        )
    tag_target = subprocess.run(
        ("git", "-C", str(project), "rev-list", "-n", "1", FROZEN_TAG),
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    return {
        "components": components,
        "freeze_manifest_actual_sha256": freeze_sha,
        "freeze_manifest_expected_sha256": suite["freeze_manifest"]["sha256"],
        "pass": freeze_sha == suite["freeze_manifest"]["sha256"]
        and tag_target == FROZEN_HARNESS_COMMIT
        and all(row["pass"] for row in components),
        "tag_target": tag_target,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite-manifest",
        type=Path,
        default=ROOT / "qualification/qwen32b-v1/suite-manifest.json",
    )
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args(argv)
    output = arguments.output_directory
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"CPU preflight output already exists: {output}")
    output.mkdir(parents=True, mode=0o700)
    result: dict[str, Any] = {
        "checks": {},
        "created_at_utc": datetime.now(UTC).isoformat(),
        "overall": "FAIL",
        "schema": "qwen32b-qualification-cpu-preflight-v1",
    }
    try:
        project = ROOT.resolve(strict=True)
        suite = load_suite_manifest(arguments.suite_manifest)
        task_records = []
        for suite_task in suite["tasks"]:
            path = project / suite_task["manifest_path"]
            manifest_hash_ok = sha256_file(path) == suite_task["manifest_sha256"]
            task = load_json(path)
            record = _task_gate(project, task, output)
            record["suite_manifest_hash_match"] = manifest_hash_ok
            record["pass"] = record["pass"] and manifest_hash_ok
            task_records.append(record)
        result["tasks"] = task_records
        result["checks"]["all_task_gates"] = all(row["pass"] for row in task_records)

        freeze = _verify_freeze(project, suite)
        write_canonical_json(output / "freeze-verification.json", freeze)
        result["checks"]["freeze_manifest_verification"] = freeze["pass"]

        finalizer_tests = _run(
            (
                str(CMPILOT_PYTHON),
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "tests/test_calculator_finalizer.py::test_every_model_termination_path_completes_total_finalization",
            ),
            cwd=project,
            prefix=output / "finalizer-termination-tests",
        )
        result["checks"]["finalizer_all_termination_classes"] = (
            finalizer_tests["exit_code"] == 0 and finalizer_tests["passed"] == 10
        )
        result["finalizer_tests"] = finalizer_tests

        regression = _run(
            (
                str(CMPILOT_PYTHON),
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "tests/test_action_protocol.py",
                "tests/test_action_protocol_matrix.py",
                "tests/test_command_authorization.py",
                "tests/test_command_authorization_runtime.py",
                "tests/test_context_budget.py",
                "tests/test_protected_path_policy.py",
                "tests/test_protected_path_runtime.py",
            ),
            cwd=project,
            prefix=output / "parser-authorization-regressions",
        )
        result["checks"]["parser_authorization_regressions"] = (
            regression["exit_code"] == 0
        )
        result["regression_tests"] = regression

        project_tests = _run(
            (
                str(CMPILOT_PYTHON),
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
            ),
            cwd=project,
            prefix=output / "project-tests",
        )
        result["checks"]["complete_project_test_suite"] = (
            project_tests["exit_code"] == 0 and project_tests["failed"] == 0
        )
        result["project_tests"] = project_tests

        batch = project / "slurm/qwen32b_qualification_task.sbatch"
        syntax = _run(
            ("/usr/bin/bash", "-n", str(batch)),
            cwd=project,
            prefix=output / "batch-syntax",
        )
        script = batch.read_text(encoding="utf-8")
        required_directives = (
            "#SBATCH --partition=gpu",
            "#SBATCH --gres=gpu:a100:2",
            "#SBATCH --nodes=1",
            "#SBATCH --no-requeue",
        )
        controller_ready = (
            syntax["exit_code"] == 0
            and all(script.splitlines().count(item) == 1 for item in required_directives)
            and "submit_attested_batch.py" not in script
            and "{{" not in script
            and "TODO" not in script
        )
        result["checks"]["controller_attestation_preparation"] = controller_ready
        result["controller_attestation_preparation"] = {
            "script": str(batch),
            "script_sha256": sha256_file(batch),
            "syntax": syntax,
        }

        project_status = subprocess.run(
            ("git", "-C", str(project), "status", "--short"),
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        result["project_status"] = project_status
        result["checks"]["no_unresolved_placeholders"] = all(
            "{{" not in path.read_text(encoding="utf-8")
            and "{%" not in path.read_text(encoding="utf-8")
            and "TODO" not in path.read_text(encoding="utf-8")
            for path in [
                arguments.suite_manifest,
                project / suite["freeze_manifest"]["path"],
                batch,
            ]
        )
        result["checks"]["gpu_disabled_for_cpu_gate"] = (
            os.environ.get("CUDA_VISIBLE_DEVICES", "") in {"", "-1"}
        )
        result["checks"]["absence_of_package_install_or_network"] = all(
            row["checks"]["no_package_or_network_requirement"]
            for row in task_records
        )
        result["checks"]["artifact_paths"] = all(
            row["checks"]["artifact_path"] for row in task_records
        )
        result["checks"]["canonical_prompt_rendering"] = all(
            row["checks"]["canonical_prompt_rendering"] for row in task_records
        )
        result["checks"]["no_memory_or_residual_conversation"] = all(
            row["checks"]["no_memory_or_residual_state"] for row in task_records
        )
        result["overall"] = "PASS" if all(result["checks"].values()) else "FAIL"
    except BaseException as error:
        result["error"] = f"{type(error).__name__}: {error}"
        result["traceback"] = traceback.format_exc()

    write_canonical_json(output / "cpu-preflight-result.json", result)
    manifest = artifact_manifest(
        output, excluded=("artifact-manifest.json", "artifact-manifest.sha256")
    )
    write_canonical_json(output / "artifact-manifest.json", manifest)
    (output / "artifact-manifest.sha256").write_text(
        sha256_file(output / "artifact-manifest.json") + "\n", encoding="ascii"
    )
    print(json.dumps({"overall": result["overall"], "output": str(output)}, sort_keys=True))
    return 0 if result["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
