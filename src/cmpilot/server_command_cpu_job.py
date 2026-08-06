"""Stage the shared-storage CPU Slurm gate for server-command extraction."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Sequence

from cmpilot.file_digest import sha256_file
from cmpilot.guided_backend import write_qwen32b_load_gate_plan
from cmpilot.server_command import audit_external_executables
from cmpilot.shared_runtime import (
    DEFAULT_SHARED_ROOTS,
    StagedRuntimeDriver,
    render_cpu_gate_wrapper,
    stage_runtime_driver,
    validate_script_executables,
    validate_script_runtime_paths,
)


VLLM_PYTHON = Path("/home/s224049759/environments/vllm-smoke/bin/python")
CMPILOT_PYTHON = Path("/home/s224049759/environments/cmpilot-conda/bin/python")
DEFAULT_ARTIFACT_ROOT = Path(
    "/home/s224049759/run-artifacts/server-command-extraction"
)


@dataclass(frozen=True)
class ServerCommandCpuGateBundle:
    pre_submit_directory: Path
    driver: StagedRuntimeDriver
    submitted_script: Path
    submitted_script_sha256: str
    runtime_manifest: Path
    command_plan: Path
    command_plan_sha256: str


def required_project_runtime_files(project_root: Path) -> tuple[Path, ...]:
    """Files directly loaded by the CPU driver and its targeted tests."""
    relative_paths = (
        "pyproject.toml",
        "src/cmpilot/__init__.py",
        "src/cmpilot/batch_script_attestation.py",
        "src/cmpilot/file_digest.py",
        "src/cmpilot/environment_content_digest.py",
        "src/cmpilot/environment_fingerprint.py",
        "src/cmpilot/guided_backend.py",
        "src/cmpilot/guided_backend_cpu_job.py",
        "src/cmpilot/server_command.py",
        "src/cmpilot/server_command_cpu_job.py",
        "src/cmpilot/shared_runtime.py",
        "scripts/batch_script_attestation.py",
        "scripts/extract_server_command.py",
        "scripts/guided_backend_cpu_gate.py",
        "scripts/server_command_cpu_gate.py",
        "tests/test_batch_script_attestation.py",
        "tests/test_environment_content_digest.py",
        "tests/test_environment_fingerprint.py",
        "tests/test_guided_backend.py",
        "tests/test_server_command.py",
        "tests/test_shared_runtime.py",
        "tests/fixtures/job_25033_packages_batch.json",
        "tests/fixtures/job_25033_packages_login.json",
        "tests/fixtures/job_25042_guided_backend_traceback.txt",
        "tests/fixtures/job_25042_server_command.txt",
        "tests/fixtures/job_25264_slurm.stderr",
        "tests/fixtures/job_25264_submitted_excerpt.sbatch",
        "tests/fixtures/job_25335_server_command.json",
        "tests/fixtures/job_25335_slurm.stderr",
        "tests/fixtures/job_25335_submitted_excerpt.sbatch",
        "tests/fixtures/job_25371_attestation.json",
        "tests/fixtures/job_25371_submitted_excerpt.sbatch",
    )
    project_files = tuple(project_root / relative for relative in relative_paths)
    historical_files = (
        Path(
            "/home/s224049759/run-artifacts/guided-backend-fix/25264/forensics/"
            "installed-package-files.json"
        ),
        Path(
            "/home/s224049759/run-artifacts/guided-backend-fix/25264/forensics/"
            "installed-package-summary.json"
        ),
    )
    return project_files + historical_files


def stage_server_command_cpu_gate(
    *,
    project_root: Path,
    pre_submit_directory: Path,
    expected_environment_fingerprint: str,
    expected_content_digest: str,
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
    shared_roots: Sequence[Path] = DEFAULT_SHARED_ROOTS,
    job_name: str = "server-command-extraction",
) -> ServerCommandCpuGateBundle:
    """Stage an immutable driver and validated CPU-only Slurm wrapper."""
    project_root = project_root.resolve(strict=True)
    driver = stage_runtime_driver(
        project_root / "scripts" / "server_command_cpu_gate.py",
        pre_submit_directory,
        shared_roots=shared_roots,
        destination_name="server-command-cpu-gate.py",
    )
    plan = write_qwen32b_load_gate_plan(
        driver.path.parent / "server-command-plan",
        port=49773,
    )
    for plan_path in (
        plan.command_json,
        plan.command_metadata,
        plan.command_text,
        plan.effective_configuration,
        plan.request_json,
        plan.run_manifest,
    ):
        plan_path.chmod(0o444)
    command_plan = StagedRuntimeDriver(
        path=plan.command_json,
        sha256=sha256_file(plan.command_json),
        source=plan.command_json,
    )
    submitted_script = driver.path.parent / "server-command-cpu-gate.sbatch"
    wrapper = render_cpu_gate_wrapper(
        driver_path=driver.path,
        driver_sha256=driver.sha256,
        artifact_root=artifact_root,
        driver_interpreter=VLLM_PYTHON,
        driver_arguments=(
            "--project-root",
            str(project_root),
            "--expected-environment-fingerprint",
            expected_environment_fingerprint,
            "--expected-content-digest",
            expected_content_digest,
            "--command-plan",
            str(command_plan.path),
            "--expected-command-plan-sha256",
            command_plan.sha256,
            "--cmpilot-python",
            str(CMPILOT_PYTHON),
        ),
        required_runtime_paths=required_project_runtime_files(project_root),
        strict_runtime_inputs=(command_plan,),
        digest_tool=project_root / "scripts" / "batch_script_attestation.py",
        digest_interpreter=CMPILOT_PYTHON,
        submitted_script_path=submitted_script,
        shared_roots=shared_roots,
        job_name=job_name,
    )
    submitted_script.write_text(wrapper, encoding="utf-8", newline="\n")
    submitted_script.chmod(0o444)
    validated_paths = validate_script_runtime_paths(
        wrapper, shared_roots=shared_roots
    )
    validated_executables = validate_script_executables(wrapper)
    if "/usr/bin/jq" in wrapper or re_bare_jq(wrapper):
        raise ValueError("generated CPU gate must not depend on jq")
    dependency_audit = audit_external_executables(scope="cpu", inside_job=False)
    if not dependency_audit["pass"] or dependency_audit["jq_required"]:
        raise ValueError("CPU executable pre-submission audit failed")
    submitted_digest = sha256_file(submitted_script)
    runtime_manifest = driver.path.parent / "runtime-manifest.json"
    runtime_manifest.write_text(
        json.dumps(
            {
                "artifact_root": str(artifact_root),
                "dependency_audit": dependency_audit,
                "driver": {"path": str(driver.path), "sha256": driver.sha256},
                "command_plan": {
                    "path": str(command_plan.path),
                    "sha256": command_plan.sha256,
                },
                "expected_content_digest": expected_content_digest,
                "expected_environment_fingerprint": expected_environment_fingerprint,
                "mandatory_executables": [
                    str(path) for path in validated_executables
                ],
                "runtime_files": [str(path) for path in validated_paths],
                "schema": "server-command-cpu-gate-bundle-v2",
                "submitted_script": {
                    "path": str(submitted_script),
                    "sha256": submitted_digest,
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    runtime_manifest.chmod(0o444)
    return ServerCommandCpuGateBundle(
        pre_submit_directory=driver.path.parent,
        driver=driver,
        submitted_script=submitted_script,
        submitted_script_sha256=submitted_digest,
        runtime_manifest=runtime_manifest,
        command_plan=command_plan.path,
        command_plan_sha256=command_plan.sha256,
    )


def re_bare_jq(script: str) -> bool:
    """Detect an executable token named jq without matching unrelated text."""
    return any(
        token == "jq"
        for line in script.splitlines()
        for token in line.strip().split()
    )
