"""Read-only forensics and visible-test investigation for calculator job 25692."""

from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
from typing import Any, Sequence

from .calculator_finalizer import inspect_shell_finalizer_control_flow


MODEL_TEST_COMMAND_CHOICE = "MODEL_TEST_COMMAND_CHOICE"
VISIBLE_TEST_EXECUTION_DEFECT = "VISIBLE_TEST_EXECUTION_DEFECT"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def classify_visible_test_source(source: str) -> dict[str, Any]:
    """Classify test definitions without importing or executing the file."""
    tree = ast.parse(source)
    top_level_tests = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test")
    ]
    test_case_classes: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {
            ast.unparse(base) if hasattr(ast, "unparse") else ""
            for base in node.bases
        }
        if "unittest.TestCase" in bases or "TestCase" in bases:
            test_case_classes.append(node.name)
    if top_level_tests and not test_case_classes:
        style = "pytest-style-top-level-functions"
    elif test_case_classes:
        style = "unittest-test-case-style"
    else:
        style = "unknown"
    return {
        "style": style,
        "top_level_test_functions": top_level_tests,
        "unittest_test_case_classes": test_case_classes,
    }


def _run(
    name: str,
    arguments: Sequence[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    output_directory: Path,
) -> dict[str, Any]:
    completed = subprocess.run(
        list(arguments),
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )
    record = {
        "name": name,
        "argv": list(arguments),
        "cwd": str(cwd),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    _write_json(output_directory / f"{name}.json", record)
    (output_directory / f"{name}.stdout").write_text(
        completed.stdout, encoding="utf-8", newline="\n"
    )
    (output_directory / f"{name}.stderr").write_text(
        completed.stderr, encoding="utf-8", newline="\n"
    )
    (output_directory / f"{name}.exit").write_text(
        f"{completed.returncode}\n", encoding="ascii", newline="\n"
    )
    return record


def run_visible_test_investigation(
    *,
    working_copy: Path,
    output_directory: Path,
    agent_python: Path,
    baseline_python: Path,
) -> dict[str, Any]:
    """Run the exact job-25692 test-command matrix in an expendable copy."""
    working_copy = working_copy.resolve(strict=True)
    output_directory.mkdir(parents=True, exist_ok=False)
    test_path = working_copy / "test_calculator.py"
    source = test_path.read_text(encoding="utf-8")
    source_classification = classify_visible_test_source(source)
    test_hash_before = _sha256(test_path)
    test_mode_before = format(stat.S_IMODE(test_path.stat().st_mode), "04o")

    agent_home = output_directory / "agent-home"
    agent_tmp = output_directory / "agent-tmp"
    agent_home.mkdir(mode=0o700)
    agent_tmp.mkdir(mode=0o700)
    path_value = (
        f"{agent_python.parent}:/usr/local/bin:/usr/bin:/bin"
    )
    environment = os.environ.copy()
    environment.update(
        {
            "HOME": str(agent_home),
            "PATH": path_value,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "TMPDIR": str(agent_tmp),
        }
    )
    python_command = shutil.which("python", path=path_value)
    python3_command = shutil.which("python3", path=path_value)
    if python_command is None or python3_command is None:
        raise FileNotFoundError("agent python/python3 command is unavailable")

    commands = {
        "unittest-module": (
            python_command,
            "-m",
            "unittest",
            "test_calculator.py",
        ),
        "unittest-module-python3": (
            python3_command,
            "-m",
            "unittest",
            "test_calculator.py",
        ),
        "unittest-discover": (
            python_command,
            "-m",
            "unittest",
            "discover",
            "-s",
            ".",
            "-p",
            "test_*.py",
        ),
        "baseline-pytest": (
            str(baseline_python),
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
        ),
        "immutable-oracle-pytest": (
            str(baseline_python),
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "test_calculator.py",
        ),
    }
    results = {
        name: _run(
            name,
            arguments,
            cwd=working_copy,
            environment=environment,
            output_directory=output_directory,
        )
        for name, arguments in commands.items()
    }
    unittest_zero = all(
        result["returncode"] == 0
        and re.search(r"Ran 0 tests", result["stdout"] + result["stderr"])
        for name, result in results.items()
        if name.startswith("unittest")
    )
    pytest_three = all(
        result["returncode"] == 0
        and re.search(r"3 passed", result["stdout"] + result["stderr"])
        for name, result in results.items()
        if name.endswith("pytest")
    )
    model_choice = (
        source_classification["style"] == "pytest-style-top-level-functions"
        and unittest_zero
        and pytest_three
    )
    result = {
        "schema": "job-25692-visible-test-investigation-v1",
        "classification": (
            MODEL_TEST_COMMAND_CHOICE
            if model_choice
            else VISIBLE_TEST_EXECUTION_DEFECT
        ),
        "fixture_correction_required": not model_choice,
        "source_classification": source_classification,
        "test_path": str(test_path),
        "test_contents": source,
        "test_sha256_before": test_hash_before,
        "test_sha256_after": _sha256(test_path),
        "test_mode_before": test_mode_before,
        "test_mode_after": format(
            stat.S_IMODE(test_path.stat().st_mode), "04o"
        ),
        "test_unchanged": test_hash_before == _sha256(test_path),
        "permissions_prevented_execution": False if pytest_three else None,
        "agent_python": python_command,
        "agent_python3": python3_command,
        "baseline_python": str(baseline_python),
        "working_directory": str(working_copy),
        "unittest_zero_tests": unittest_zero,
        "pytest_three_passed": pytest_three,
        "commands": results,
    }
    _write_json(output_directory / "visible-test-investigation.json", result)
    return result


def collect_job_25692_forensics(job_artifacts: Path) -> dict[str, Any]:
    """Collect evidence without writing to the historical artifact directory."""
    root = job_artifacts.resolve(strict=True)
    script_path = root / "submitted-calculator-diagnostic.sbatch"
    script = script_path.read_text(encoding="utf-8")
    analysis = json.loads((root / "agent-analysis.json").read_text(encoding="utf-8"))
    baseline = json.loads((root / "calculator-baseline.json").read_text(encoding="utf-8"))
    test_path = root / "final-working-tree" / "test_calculator.py"
    test_source = test_path.read_text(encoding="utf-8")
    external = analysis["external_oracle_result"]
    missing_finalizer_outputs = [
        name
        for name in (
            "post-agent-outer-failure-count.txt",
            "memory-summary.json",
            "authoritative-result.txt",
            "artifact-preservation-pass-1.json",
            "artifact-preservation-pass-2.json",
            "artifact-preservation-idempotency.json",
            "scratch-cleanup.json",
            "sha256-manifest.txt",
            "manifest-validation.json",
        )
        if not (root / name).exists()
    ]
    return {
        "schema": "job-25692-forensic-review-v1",
        "job_id": "25692",
        "historical_artifacts": str(root),
        "historical_result_unchanged": True,
        "submitted_script_sha256": _sha256(script_path),
        "unbound_variable_traceback": (
            "POST_AGENT_FAILURE_COUNT: unbound variable"
        ),
        "unbound_variable_line": 1196,
        "finalizer_control_flow": inspect_shell_finalizer_control_flow(script),
        "missing_finalizer_outputs": missing_finalizer_outputs,
        "visible_test": {
            "contents": test_source,
            "sha256": _sha256(test_path),
            "mode": format(stat.S_IMODE(test_path.stat().st_mode), "04o"),
            "classification": classify_visible_test_source(test_source),
        },
        "baseline_command": baseline["test_command"],
        "immutable_oracle_command": external["command"],
        "retrospective_capability": {
            "repository_solution_capability": "demonstrated",
            "authorized_calculator_patch": True,
            "allowed_patch_only": external["disallowed_diff"] == "",
            "immutable_oracle_passed": (
                external["passed"] == 3 and external["failed"] == 0
            ),
            "protected_or_disallowed_modification": False,
            "agent_submitted_completion": analysis[
                "completion_sentinel_recorded"
            ],
            "model_run_termination": analysis["termination_reason"],
            "original_technical_validity": "fail",
            "original_result_rewritten": False,
        },
    }
