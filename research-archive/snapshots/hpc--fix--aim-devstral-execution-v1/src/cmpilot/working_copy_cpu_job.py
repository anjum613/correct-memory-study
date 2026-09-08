"""Generate and lint the isolated-working-copy CPU Slurm validation gate."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import io
import json
import os
from pathlib import Path
import re
import runpy
import shlex
import subprocess
from typing import Iterable, Iterator, Sequence

from cmpilot.file_digest import sha256_file, validate_sha256_hex
from cmpilot.shared_runtime import (
    DEFAULT_SHARED_ROOTS,
    StagedRuntimeDriver,
    render_cpu_gate_wrapper,
    stage_runtime_driver,
    validate_script_executables,
    validate_script_runtime_paths,
)


CPU_GATE_SCRIPT_GENERATION_FAILURE = "CPU_GATE_SCRIPT_GENERATION_FAILURE"
GENERATED_SCRIPT_ARGUMENT_VALIDATION_FAILURE = (
    "GENERATED_SCRIPT_ARGUMENT_VALIDATION_FAILURE"
)
CMPILOT_PYTHON = Path("/home/s224049759/environments/cmpilot-conda/bin/python")
VLLM_PYTHON = Path("/home/s224049759/environments/vllm-smoke/bin/python")
DEFAULT_ARTIFACT_ROOT = Path(
    "/home/s224049759/run-artifacts/working-copy-permissions"
)
_REQUIRED_DRIVER_OPTIONS = (
    "--cmpilot-python",
    "--vllm-python",
    "--project-root",
    "--source-fixture",
    "--model-cache-root",
    "--expected-environment-fingerprint",
    "--expected-runtime-content-digest",
    "--expected-model-cache-digest",
)
_PATCH_MARKER = re.compile(r"^(?:\+\++|---)(?:\s|$)|^@@(?:\s|$)")
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


class GeneratedScriptArgumentError(ValueError):
    """A generated batch script or structured argv is unsafe to submit."""


@dataclass(frozen=True)
class WorkingCopyCpuGateBundle:
    pre_submit_directory: Path
    driver: StagedRuntimeDriver
    driver_arguments: tuple[str, ...]
    submitted_script: Path
    submitted_script_sha256: str
    runtime_manifest: Path
    script_validation: dict[str, object]


def render_shell_argv(
    arguments: Iterable[str],
    *,
    allowed_literal_plus_indices: frozenset[int] = frozenset(),
) -> str:
    """Quote a structural argv without losing spaces, quotes, or newlines."""
    values = tuple(arguments)
    if not values:
        raise GeneratedScriptArgumentError("command argv must not be empty")
    for index, value in enumerate(values):
        if not isinstance(value, str):
            raise GeneratedScriptArgumentError(
                f"command argument {index} is not a string"
            )
        if "\0" in value:
            raise GeneratedScriptArgumentError(
                f"command argument {index} contains a null byte"
            )
        if value == "+" and index not in allowed_literal_plus_indices:
            raise GeneratedScriptArgumentError(
                f"command argument {index} is an unintended standalone plus"
            )
    return shlex.join(values)


def _logical_shell_commands(script: str) -> Iterator[tuple[int, str]]:
    """Yield shell commands while excluding literal here-document bodies."""
    lines = script.splitlines()
    index = 0
    while index < len(lines):
        line_number = index + 1
        line = lines[index]
        stripped = line.strip()
        index += 1
        if not stripped or stripped.startswith("#"):
            continue
        parts = [line]
        while parts[-1].rstrip().endswith("\\") and index < len(lines):
            parts[-1] = parts[-1].rstrip()[:-1]
            parts.append(lines[index])
            index += 1
        command = "\n".join(parts)
        yield line_number, command
        match = _HEREDOC.search(command)
        if match is not None:
            delimiter = match.group(2)
            while index < len(lines):
                body_line = lines[index]
                index += 1
                if body_line.strip() == delimiter:
                    break


def analyze_generated_script(script: str) -> dict[str, object]:
    """Find accidental patch tokens and shell-tokenization failures."""
    standalone_plus_by_line: list[dict[str, object]] = []
    patch_markers: list[dict[str, object]] = []
    tokenization_errors: list[dict[str, object]] = []
    for line_number, command in _logical_shell_commands(script):
        stripped = command.lstrip()
        if _PATCH_MARKER.match(stripped):
            patch_markers.append({"line": line_number, "text": command})
        try:
            tokens = shlex.split(command, comments=True, posix=True)
        except ValueError as error:
            tokenization_errors.append(
                {"error": str(error), "line": line_number, "text": command}
            )
            continue
        plus_count = sum(token == "+" for token in tokens)
        if plus_count:
            standalone_plus_by_line.append(
                {"count": plus_count, "line": line_number, "text": command}
            )
    return {
        "patch_marker_count": len(patch_markers),
        "patch_markers": patch_markers,
        "schema": "generated-batch-script-analysis-v1",
        "standalone_plus_by_line": standalone_plus_by_line,
        "standalone_plus_count": sum(
            int(row["count"]) for row in standalone_plus_by_line
        ),
        "tokenization_error_count": len(tokenization_errors),
        "tokenization_errors": tokenization_errors,
    }


def build_working_copy_driver_arguments(
    *,
    project_root: Path,
    source_fixture: Path,
    model_cache_root: Path,
    cmpilot_python: Path,
    vllm_python: Path,
    expected_environment_fingerprint: str,
    expected_runtime_content_digest: str,
    expected_model_cache_digest: str,
) -> tuple[str, ...]:
    """Build the driver argv as data, never as copied multiline shell text."""
    return (
        "--cmpilot-python",
        str(cmpilot_python),
        "--vllm-python",
        str(vllm_python),
        "--project-root",
        str(project_root),
        "--source-fixture",
        str(source_fixture),
        "--model-cache-root",
        str(model_cache_root),
        "--expected-environment-fingerprint",
        expected_environment_fingerprint,
        "--expected-runtime-content-digest",
        expected_runtime_content_digest,
        "--expected-model-cache-digest",
        expected_model_cache_digest,
    )


def validate_working_copy_driver_arguments(
    arguments: Sequence[str],
    *,
    parser: argparse.ArgumentParser,
) -> dict[str, object]:
    """Parse the generated argv with the driver's actual argparse parser."""
    values = tuple(arguments)
    try:
        render_shell_argv(values)
    except GeneratedScriptArgumentError as error:
        raise GeneratedScriptArgumentError(
            f"{GENERATED_SCRIPT_ARGUMENT_VALIDATION_FAILURE}: {error}"
        ) from error
    counts = {option: values.count(option) for option in _REQUIRED_DRIVER_OPTIONS}
    invalid_counts = {option: count for option, count in counts.items() if count != 1}
    if invalid_counts:
        raise GeneratedScriptArgumentError(
            f"{GENERATED_SCRIPT_ARGUMENT_VALIDATION_FAILURE}: "
            f"required option counts are invalid: {invalid_counts}"
        )
    error_stream = io.StringIO()
    try:
        from contextlib import redirect_stderr

        with redirect_stderr(error_stream):
            parsed = parser.parse_args(values)
    except SystemExit as error:
        detail = error_stream.getvalue().strip()
        raise GeneratedScriptArgumentError(
            f"{GENERATED_SCRIPT_ARGUMENT_VALIDATION_FAILURE}: "
            f"driver argparse rejected argv with exit {error.code}: {detail}"
        ) from error
    for attribute in (
        "cmpilot_python",
        "vllm_python",
        "project_root",
        "source_fixture",
        "model_cache_root",
    ):
        path = Path(getattr(parsed, attribute))
        if not path.is_absolute():
            raise GeneratedScriptArgumentError(
                f"{GENERATED_SCRIPT_ARGUMENT_VALIDATION_FAILURE}: "
                f"{attribute} is not absolute: {path}"
            )
    for attribute in (
        "expected_environment_fingerprint",
        "expected_runtime_content_digest",
        "expected_model_cache_digest",
    ):
        try:
            validate_sha256_hex(getattr(parsed, attribute), name=attribute)
        except ValueError as error:
            raise GeneratedScriptArgumentError(
                f"{GENERATED_SCRIPT_ARGUMENT_VALIDATION_FAILURE}: {error}"
            ) from error
    return {
        "argument_count": len(values),
        "arguments": list(values),
        "expected_environment_fingerprint": parsed.expected_environment_fingerprint,
        "expected_model_cache_digest": parsed.expected_model_cache_digest,
        "expected_runtime_content_digest": parsed.expected_runtime_content_digest,
        "schema": "working-copy-driver-argument-validation-v1",
    }


def _extract_rendered_driver_arguments(script: str) -> tuple[str, ...]:
    matches: list[tuple[str, ...]] = []
    for _, command in _logical_shell_commands(script):
        try:
            tokens = tuple(shlex.split(command, comments=True, posix=True))
        except ValueError:
            continue
        if len(tokens) >= 3 and tokens[:3] == (
            "exec",
            "$DRIVER_INTERPRETER",
            "$DRIVER_PATH",
        ):
            matches.append(tokens[3:])
    if len(matches) != 1:
        raise GeneratedScriptArgumentError(
            f"{GENERATED_SCRIPT_ARGUMENT_VALIDATION_FAILURE}: "
            f"expected one driver invocation, found {len(matches)}"
        )
    return matches[0]


def validate_generated_script(
    script_path: Path,
    *,
    expected_driver_arguments: Sequence[str],
    parser: argparse.ArgumentParser,
) -> dict[str, object]:
    """Fail closed before sbatch for syntax, patch, or argv-generation defects."""
    script_path = Path(script_path)
    if not script_path.is_file():
        raise GeneratedScriptArgumentError(
            f"{GENERATED_SCRIPT_ARGUMENT_VALIDATION_FAILURE}: "
            f"generated script is missing: {script_path}"
        )
    script = script_path.read_text(encoding="utf-8")
    syntax = subprocess.run(
        ["/usr/bin/bash", "-n", str(script_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if syntax.returncode != 0:
        raise GeneratedScriptArgumentError(
            f"{GENERATED_SCRIPT_ARGUMENT_VALIDATION_FAILURE}: bash -n failed: "
            f"{syntax.stderr.strip()}"
        )
    analysis = analyze_generated_script(script)
    if any(
        int(analysis[key])
        for key in (
            "standalone_plus_count",
            "patch_marker_count",
            "tokenization_error_count",
        )
    ):
        raise GeneratedScriptArgumentError(
            f"{GENERATED_SCRIPT_ARGUMENT_VALIDATION_FAILURE}: "
            f"generated script analysis failed: {analysis}"
        )
    extracted = _extract_rendered_driver_arguments(script)
    expected = tuple(expected_driver_arguments)
    if extracted != expected:
        raise GeneratedScriptArgumentError(
            f"{GENERATED_SCRIPT_ARGUMENT_VALIDATION_FAILURE}: "
            f"rendered driver arguments differ: expected={expected!r} "
            f"observed={extracted!r}"
        )
    argument_report = validate_working_copy_driver_arguments(
        extracted, parser=parser
    )
    return {
        **analysis,
        "bash_syntax": "PASS",
        "driver_argument_count": argument_report["argument_count"],
        "driver_arguments": argument_report["arguments"],
        "schema": "generated-working-copy-script-validation-v1",
    }


def classify_cpu_gate_script_failure(*, stderr: str, script: str) -> str | None:
    """Classify job 25517 without attributing the failure to repository copying."""
    analysis = analyze_generated_script(script)
    if (
        "unrecognized arguments:" in stderr
        and "+" in stderr.partition("unrecognized arguments:")[2].split()
        and int(analysis["standalone_plus_count"]) > 0
    ):
        return CPU_GATE_SCRIPT_GENERATION_FAILURE
    return None


def required_project_runtime_files(project_root: Path) -> tuple[Path, ...]:
    relative_paths = (
        "pyproject.toml",
        "src/cmpilot/__init__.py",
        "src/cmpilot/batch_script_attestation.py",
        "src/cmpilot/file_digest.py",
        "src/cmpilot/environment_content_digest.py",
        "src/cmpilot/environment_fingerprint.py",
        "src/cmpilot/repository_manager.py",
        "src/cmpilot/shared_runtime.py",
        "src/cmpilot/working_copy_cpu_job.py",
        "scripts/batch_script_attestation.py",
        "scripts/environment_content_digest.py",
        "scripts/environment_fingerprint.py",
        "scripts/working_copy_cpu_gate.py",
        "tests/test_batch_script_attestation.py",
        "tests/test_command_authorization.py",
        "tests/test_repository_copy_permissions.py",
        "tests/test_shared_runtime.py",
        "tests/test_working_copy_cpu_job.py",
        "tests/fixtures/job_25517_submitted_excerpt.sbatch",
    )
    return tuple(project_root / relative for relative in relative_paths)


def _driver_parser(driver_source: Path) -> argparse.ArgumentParser:
    namespace = runpy.run_path(str(driver_source), run_name="working_copy_driver_lint")
    builder = namespace.get("build_parser")
    if not callable(builder):
        raise GeneratedScriptArgumentError(
            f"{GENERATED_SCRIPT_ARGUMENT_VALIDATION_FAILURE}: "
            "driver does not expose build_parser"
        )
    parser = builder()
    if not isinstance(parser, argparse.ArgumentParser):
        raise GeneratedScriptArgumentError(
            f"{GENERATED_SCRIPT_ARGUMENT_VALIDATION_FAILURE}: "
            "build_parser did not return ArgumentParser"
        )
    return parser


def stage_working_copy_cpu_gate(
    *,
    project_root: Path,
    pre_submit_directory: Path,
    source_fixture: Path,
    model_cache_root: Path,
    expected_environment_fingerprint: str,
    expected_runtime_content_digest: str,
    expected_model_cache_digest: str,
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
    cmpilot_python: Path = CMPILOT_PYTHON,
    vllm_python: Path = VLLM_PYTHON,
    shared_roots: Sequence[Path] = DEFAULT_SHARED_ROOTS,
) -> WorkingCopyCpuGateBundle:
    """Stage, hash, render, and lint one CPU-only working-copy gate."""
    project_root = project_root.resolve(strict=True)
    source_fixture = source_fixture.resolve(strict=True)
    model_cache_root = model_cache_root.resolve(strict=True)
    driver_source = project_root / "scripts" / "working_copy_cpu_gate.py"
    parser = _driver_parser(driver_source)
    arguments = build_working_copy_driver_arguments(
        project_root=project_root,
        source_fixture=source_fixture,
        model_cache_root=model_cache_root,
        cmpilot_python=cmpilot_python,
        vllm_python=vllm_python,
        expected_environment_fingerprint=expected_environment_fingerprint,
        expected_runtime_content_digest=expected_runtime_content_digest,
        expected_model_cache_digest=expected_model_cache_digest,
    )
    argument_report = validate_working_copy_driver_arguments(
        arguments, parser=parser
    )
    driver = stage_runtime_driver(
        driver_source,
        pre_submit_directory,
        shared_roots=shared_roots,
        destination_name="working-copy-cpu-gate.py",
    )
    runtime_files = required_project_runtime_files(project_root)
    strict_inputs = tuple(
        StagedRuntimeDriver(
            path=path.resolve(strict=True),
            sha256=sha256_file(path.resolve(strict=True)),
            source=path.resolve(strict=True),
        )
        for path in runtime_files
    )
    submitted_script = driver.path.parent / "working-copy-permissions.sbatch"
    wrapper = render_cpu_gate_wrapper(
        driver_path=driver.path,
        driver_sha256=driver.sha256,
        artifact_root=artifact_root,
        driver_interpreter=cmpilot_python,
        driver_arguments=arguments,
        strict_runtime_inputs=strict_inputs,
        digest_tool=project_root / "scripts" / "batch_script_attestation.py",
        digest_interpreter=cmpilot_python,
        submitted_script_path=submitted_script,
        shared_roots=shared_roots,
        job_name="working-copy-permissions",
    )
    submitted_script.write_text(wrapper, encoding="utf-8", newline="\n")
    submitted_script.chmod(0o444)
    script_validation = validate_generated_script(
        submitted_script,
        expected_driver_arguments=arguments,
        parser=parser,
    )
    validated_paths = validate_script_runtime_paths(
        wrapper, shared_roots=shared_roots
    )
    validated_executables = validate_script_executables(wrapper)
    submitted_digest = sha256_file(submitted_script)
    runtime_manifest = driver.path.parent / "runtime-manifest.json"
    runtime_manifest.write_text(
        json.dumps(
            {
                "artifact_root": str(artifact_root),
                "driver": {"path": str(driver.path), "sha256": driver.sha256},
                "driver_invocation": argument_report,
                "expected_environment_fingerprint": expected_environment_fingerprint,
                "expected_model_cache_digest": expected_model_cache_digest,
                "expected_runtime_content_digest": expected_runtime_content_digest,
                "mandatory_executables": [str(path) for path in validated_executables],
                "runtime_files": [str(path) for path in validated_paths],
                "runtime_file_hashes": [
                    {"path": str(item.path), "sha256": item.sha256}
                    for item in strict_inputs
                ],
                "schema": "working-copy-cpu-gate-bundle-v1",
                "script_validation": script_validation,
                "submitted_script": {
                    "path": str(submitted_script),
                    "sha256": submitted_digest,
                },
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    runtime_manifest.chmod(0o444)
    return WorkingCopyCpuGateBundle(
        pre_submit_directory=driver.path.parent,
        driver=driver,
        driver_arguments=arguments,
        submitted_script=submitted_script,
        submitted_script_sha256=submitted_digest,
        runtime_manifest=runtime_manifest,
        script_validation=script_validation,
    )
