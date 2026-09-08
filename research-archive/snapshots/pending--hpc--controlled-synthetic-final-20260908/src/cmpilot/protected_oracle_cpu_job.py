"""Stage and structurally validate the protected-oracle CPU Slurm gate."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
from typing import Any, Sequence

from .file_digest import sha256_file, validate_sha256_hex
from .shared_runtime import (
    DEFAULT_SHARED_ROOTS,
    StagedRuntimeDriver,
    render_cpu_gate_wrapper,
    stage_runtime_driver,
    validate_script_executables,
    validate_script_runtime_paths,
)
from .working_copy_cpu_job import (
    GENERATED_SCRIPT_ARGUMENT_VALIDATION_FAILURE,
    GeneratedScriptArgumentError,
    _extract_rendered_driver_arguments,
    analyze_generated_script,
    render_shell_argv,
)


CMPILOT_PYTHON = Path("/home/s224049759/environments/cmpilot-conda/bin/python")
VLLM_PYTHON = Path("/home/s224049759/environments/vllm-smoke/bin/python")
DEFAULT_ARTIFACT_ROOT = Path("/home/s224049759/run-artifacts/protected-oracle")
DEFAULT_MODEL_CACHE = Path("/home/s224049759/model-cache/huggingface")
DEFAULT_JOB_25575 = Path(
    "/home/s224049759/run-artifacts/qwen32b-calculator/25575"
)
_REQUIRED_OPTIONS = (
    "--cmpilot-python",
    "--vllm-python",
    "--project-root",
    "--source-fixture",
    "--oracle-source",
    "--job-25575-artifacts",
    "--model-cache-root",
    "--expected-environment-fingerprint",
    "--expected-runtime-content-digest",
    "--expected-model-cache-digest",
)
_IGNORED_NAMES = frozenset(
    {
        ".git",
        ".pytest_cache",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        "tmp",
    }
)


@dataclass(frozen=True)
class ProtectedOracleCpuGateBundle:
    pre_submit_directory: Path
    driver: StagedRuntimeDriver
    driver_arguments: tuple[str, ...]
    project_snapshot: Path
    project_manifest: Path
    submitted_script: Path
    submitted_script_sha256: str
    runtime_manifest: Path
    script_validation: dict[str, Any]


def build_protected_oracle_driver_arguments(
    *,
    project_root: Path,
    source_fixture: Path,
    oracle_source: Path,
    job_25575_artifacts: Path,
    model_cache_root: Path,
    cmpilot_python: Path,
    vllm_python: Path,
    expected_environment_fingerprint: str,
    expected_runtime_content_digest: str,
    expected_model_cache_digest: str,
) -> tuple[str, ...]:
    return (
        "--cmpilot-python",
        str(cmpilot_python),
        "--vllm-python",
        str(vllm_python),
        "--project-root",
        str(project_root),
        "--source-fixture",
        str(source_fixture),
        "--oracle-source",
        str(oracle_source),
        "--job-25575-artifacts",
        str(job_25575_artifacts),
        "--model-cache-root",
        str(model_cache_root),
        "--expected-environment-fingerprint",
        expected_environment_fingerprint,
        "--expected-runtime-content-digest",
        expected_runtime_content_digest,
        "--expected-model-cache-digest",
        expected_model_cache_digest,
    )


def _driver_parser(driver_source: Path) -> argparse.ArgumentParser:
    namespace = runpy.run_path(
        str(driver_source), run_name="protected_oracle_driver_lint"
    )
    builder = namespace.get("build_parser")
    if not callable(builder):
        raise GeneratedScriptArgumentError("driver does not expose build_parser")
    parser = builder()
    if not isinstance(parser, argparse.ArgumentParser):
        raise GeneratedScriptArgumentError("build_parser did not return ArgumentParser")
    return parser


def validate_protected_oracle_driver_arguments(
    arguments: Sequence[str], *, parser: argparse.ArgumentParser
) -> dict[str, Any]:
    values = tuple(arguments)
    render_shell_argv(values)
    counts = {option: values.count(option) for option in _REQUIRED_OPTIONS}
    invalid = {option: count for option, count in counts.items() if count != 1}
    if invalid:
        raise GeneratedScriptArgumentError(
            f"{GENERATED_SCRIPT_ARGUMENT_VALIDATION_FAILURE}: {invalid}"
        )
    try:
        parsed = parser.parse_args(values)
    except SystemExit as error:
        raise GeneratedScriptArgumentError(
            f"driver argparse rejected generated arguments: {error.code}"
        ) from error
    for attribute in (
        "cmpilot_python",
        "vllm_python",
        "project_root",
        "source_fixture",
        "oracle_source",
        "job_25575_artifacts",
        "model_cache_root",
    ):
        if not Path(getattr(parsed, attribute)).is_absolute():
            raise GeneratedScriptArgumentError(f"{attribute} must be absolute")
    for attribute in (
        "expected_environment_fingerprint",
        "expected_runtime_content_digest",
        "expected_model_cache_digest",
    ):
        validate_sha256_hex(getattr(parsed, attribute), name=attribute)
    return {
        "argument_count": len(values),
        "arguments": list(values),
        "schema": "protected-oracle-driver-argument-validation-v1",
    }


def validate_protected_oracle_script(
    script_path: Path,
    *,
    expected_driver_arguments: Sequence[str],
    parser: argparse.ArgumentParser,
) -> dict[str, Any]:
    syntax = subprocess.run(
        ["/usr/bin/bash", "-n", str(script_path)],
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )
    if syntax.returncode != 0:
        raise GeneratedScriptArgumentError(f"bash -n failed: {syntax.stderr.strip()}")
    script = script_path.read_text(encoding="utf-8")
    analysis = analyze_generated_script(script)
    if any(
        int(analysis[key])
        for key in (
            "standalone_plus_count",
            "patch_marker_count",
            "tokenization_error_count",
        )
    ):
        raise GeneratedScriptArgumentError(f"generated script markers: {analysis}")
    extracted = _extract_rendered_driver_arguments(script)
    if extracted != tuple(expected_driver_arguments):
        raise GeneratedScriptArgumentError("rendered driver arguments changed")
    argument_validation = validate_protected_oracle_driver_arguments(
        extracted, parser=parser
    )
    required_directives = {
        "partition": "#SBATCH --partition=Virtual",
        "nodes": "#SBATCH --nodes=1",
        "cpus": "#SBATCH --cpus-per-task=2",
        "memory": "#SBATCH --mem=4G",
        "time": "#SBATCH --time=00:30:00",
        "requeue": "#SBATCH --no-requeue",
    }
    directive_counts = {
        name: script.splitlines().count(directive)
        for name, directive in required_directives.items()
    }
    if any(count != 1 for count in directive_counts.values()):
        raise GeneratedScriptArgumentError(
            f"CPU resource directives are invalid: {directive_counts}"
        )
    gpu_directives = [
        line
        for line in script.splitlines()
        if line.startswith("#SBATCH")
        and re.search(r"(?:gres|gpu)", line, re.IGNORECASE)
    ]
    if gpu_directives:
        raise GeneratedScriptArgumentError(
            f"CPU gate contains GPU directives: {gpu_directives}"
        )
    return {
        **analysis,
        "argument_validation": argument_validation,
        "bash_syntax": "PASS",
        "gpu_directives": gpu_directives,
        "resource_directive_counts": directive_counts,
        "schema": "protected-oracle-cpu-script-validation-v1",
    }


def _ignore(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name in _IGNORED_NAMES or name.endswith((".pyc", ".pyo"))
    }


def _snapshot_project(source: Path, destination: Path) -> dict[str, Any]:
    shutil.copytree(source, destination, ignore=_ignore, symlinks=False)
    files: list[dict[str, Any]] = []
    for path in sorted(destination.rglob("*"), key=lambda value: value.as_posix()):
        if path.is_symlink():
            raise GeneratedScriptArgumentError(
                f"staged project contains a symlink: {path}"
            )
        if path.is_file():
            path.chmod(0o444)
            files.append(
                {
                    "path": path.relative_to(destination).as_posix(),
                    "sha256": sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
            )
    directories = sorted(
        (path for path in destination.rglob("*") if path.is_dir()),
        key=lambda value: len(value.parts),
        reverse=True,
    )
    for path in directories:
        path.chmod(0o555)
    destination.chmod(0o555)
    canonical = (
        json.dumps(files, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")
    return {
        "file_count": len(files),
        "files": files,
        "inventory_sha256": hashlib.sha256(canonical).hexdigest(),
        "root": str(destination),
        "root_mode": "0555",
        "schema": "protected-oracle-project-snapshot-v1",
    }


def stage_protected_oracle_cpu_gate(
    *,
    project_root: Path,
    pre_submit_directory: Path,
    job_25575_artifacts: Path = DEFAULT_JOB_25575,
    model_cache_root: Path = DEFAULT_MODEL_CACHE,
    expected_environment_fingerprint: str,
    expected_runtime_content_digest: str,
    expected_model_cache_digest: str,
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
    cmpilot_python: Path = CMPILOT_PYTHON,
    vllm_python: Path = VLLM_PYTHON,
    shared_roots: Sequence[Path] = DEFAULT_SHARED_ROOTS,
) -> ProtectedOracleCpuGateBundle:
    project_root = project_root.resolve(strict=True)
    job_25575_artifacts = job_25575_artifacts.resolve(strict=True)
    model_cache_root = model_cache_root.resolve(strict=True)
    driver_source = project_root / "scripts" / "protected_oracle_cpu_gate.py"
    parser = _driver_parser(driver_source)
    driver = stage_runtime_driver(
        driver_source,
        pre_submit_directory,
        shared_roots=shared_roots,
        destination_name="protected-oracle-cpu-gate.py",
    )
    project_snapshot = driver.path.parent / "project-runtime"
    project_record = _snapshot_project(project_root, project_snapshot)
    project_manifest = driver.path.parent / "project-runtime-manifest.json"
    project_manifest.write_text(
        json.dumps(project_record, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    project_manifest.chmod(0o444)
    source_fixture = project_snapshot / "tasks" / "smoke_test" / "repository"
    oracle_source = project_snapshot / "oracles" / "calculator" / "v1"
    arguments = build_protected_oracle_driver_arguments(
        project_root=project_snapshot,
        source_fixture=source_fixture,
        oracle_source=oracle_source,
        job_25575_artifacts=job_25575_artifacts,
        model_cache_root=model_cache_root,
        cmpilot_python=cmpilot_python,
        vllm_python=vllm_python,
        expected_environment_fingerprint=expected_environment_fingerprint,
        expected_runtime_content_digest=expected_runtime_content_digest,
        expected_model_cache_digest=expected_model_cache_digest,
    )
    argument_validation = validate_protected_oracle_driver_arguments(
        arguments, parser=parser
    )
    strict_inputs = tuple(
        StagedRuntimeDriver(
            path=(project_snapshot / row["path"]).resolve(strict=True),
            sha256=row["sha256"],
            source=project_root / row["path"],
        )
        for row in project_record["files"]
    )
    submitted_script = driver.path.parent / "protected-oracle-cpu-gate.sbatch"
    wrapper = render_cpu_gate_wrapper(
        driver_path=driver.path,
        driver_sha256=driver.sha256,
        artifact_root=artifact_root,
        driver_interpreter=cmpilot_python,
        driver_arguments=arguments,
        strict_runtime_inputs=strict_inputs,
        digest_tool=project_snapshot / "scripts" / "batch_script_attestation.py",
        digest_interpreter=cmpilot_python,
        submitted_script_path=submitted_script,
        shared_roots=shared_roots,
        job_name="protected-oracle",
        time_limit="00:30:00",
    )
    submitted_script.write_text(wrapper, encoding="utf-8", newline="\n")
    submitted_script.chmod(0o444)
    script_validation = validate_protected_oracle_script(
        submitted_script,
        expected_driver_arguments=arguments,
        parser=parser,
    )
    validated_paths = validate_script_runtime_paths(
        wrapper, shared_roots=shared_roots
    )
    validated_executables = validate_script_executables(wrapper)
    submitted_hash = sha256_file(submitted_script)
    runtime_manifest = driver.path.parent / "runtime-manifest.json"
    runtime_manifest.write_text(
        json.dumps(
            {
                "argument_validation": argument_validation,
                "artifact_root": str(artifact_root),
                "driver": {"path": str(driver.path), "sha256": driver.sha256},
                "expected_environment_fingerprint": expected_environment_fingerprint,
                "expected_model_cache_digest": expected_model_cache_digest,
                "expected_runtime_content_digest": expected_runtime_content_digest,
                "mandatory_executables": [str(path) for path in validated_executables],
                "project_snapshot": project_record,
                "runtime_paths": [str(path) for path in validated_paths],
                "schema": "protected-oracle-cpu-gate-bundle-v1",
                "script_validation": script_validation,
                "submitted_script": {
                    "path": str(submitted_script),
                    "sha256": submitted_hash,
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    runtime_manifest.chmod(0o444)
    return ProtectedOracleCpuGateBundle(
        pre_submit_directory=driver.path.parent,
        driver=driver,
        driver_arguments=arguments,
        project_snapshot=project_snapshot,
        project_manifest=project_manifest,
        submitted_script=submitted_script,
        submitted_script_sha256=submitted_hash,
        runtime_manifest=runtime_manifest,
        script_validation=script_validation,
    )
