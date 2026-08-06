"""Generate the shared-storage CPU Slurm gate for guided backend validation."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Sequence

from cmpilot.shared_runtime import (
    DEFAULT_SHARED_ROOTS,
    StagedRuntimeDriver,
    render_cpu_gate_wrapper,
    sha256_file,
    stage_runtime_driver,
    validate_script_runtime_paths,
)


VLLM_PYTHON = Path("/home/s224049759/environments/vllm-smoke/bin/python")
CMPILOT_PYTHON = Path("/home/s224049759/environments/cmpilot-conda/bin/python")
DEFAULT_ARTIFACT_ROOT = Path(
    "/home/s224049759/run-artifacts/guided-backend-shared-path"
)


@dataclass(frozen=True)
class CpuGateBundle:
    pre_submit_directory: Path
    driver: StagedRuntimeDriver
    submitted_script: Path
    submitted_script_sha256: str
    runtime_manifest: Path


def required_project_runtime_files(project_root: Path) -> tuple[Path, ...]:
    """Files loaded directly by the driver or its targeted regression suite."""
    relative_paths = (
        "pyproject.toml",
        "src/cmpilot/__init__.py",
        "src/cmpilot/environment_content_digest.py",
        "src/cmpilot/environment_fingerprint.py",
        "src/cmpilot/guided_backend.py",
        "src/cmpilot/guided_backend_cpu_job.py",
        "src/cmpilot/shared_runtime.py",
        "scripts/guided_backend_cpu_gate.py",
        "tests/test_environment_content_digest.py",
        "tests/test_environment_fingerprint.py",
        "tests/test_guided_backend.py",
        "tests/test_shared_runtime.py",
        "tests/fixtures/job_25042_guided_backend_traceback.txt",
        "tests/fixtures/job_25042_server_command.txt",
        "tests/fixtures/job_25033_packages_batch.json",
        "tests/fixtures/job_25033_packages_login.json",
        "tests/fixtures/job_25264_slurm.stderr",
        "tests/fixtures/job_25264_submitted_excerpt.sbatch",
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


def stage_guided_backend_cpu_gate(
    *,
    project_root: Path,
    pre_submit_directory: Path,
    expected_environment_fingerprint: str,
    expected_content_digest: str,
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
    shared_roots: Sequence[Path] = DEFAULT_SHARED_ROOTS,
) -> CpuGateBundle:
    """Stage an immutable driver and render a validated CPU-only Slurm script."""
    project_root = project_root.resolve(strict=True)
    driver_source = project_root / "scripts" / "guided_backend_cpu_gate.py"
    driver = stage_runtime_driver(
        driver_source,
        pre_submit_directory,
        shared_roots=shared_roots,
        destination_name="guided-backend-cpu-gate.py",
    )
    submitted_script = driver.path.parent / "guided-backend-cpu-gate.sbatch"
    runtime_files = required_project_runtime_files(project_root)
    arguments = (
        "--project-root",
        str(project_root),
        "--expected-environment-fingerprint",
        expected_environment_fingerprint,
        "--expected-content-digest",
        expected_content_digest,
        "--cmpilot-python",
        str(CMPILOT_PYTHON),
    )
    wrapper = render_cpu_gate_wrapper(
        driver_path=driver.path,
        driver_sha256=driver.sha256,
        artifact_root=artifact_root,
        driver_interpreter=VLLM_PYTHON,
        driver_arguments=arguments,
        required_runtime_paths=runtime_files,
        submitted_script_path=submitted_script,
        shared_roots=shared_roots,
    )
    submitted_script.write_text(wrapper, encoding="utf-8", newline="\n")
    submitted_script.chmod(0o444)
    validated_paths = validate_script_runtime_paths(
        wrapper, shared_roots=shared_roots
    )
    submitted_digest = sha256_file(submitted_script)
    runtime_manifest = driver.path.parent / "runtime-manifest.json"
    runtime_manifest.write_text(
        json.dumps(
            {
                "artifact_root": str(artifact_root),
                "driver": {"path": str(driver.path), "sha256": driver.sha256},
                "expected_content_digest": expected_content_digest,
                "expected_environment_fingerprint": expected_environment_fingerprint,
                "runtime_files": [str(path) for path in validated_paths],
                "schema": "guided-backend-cpu-gate-bundle-v1",
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
    return CpuGateBundle(
        pre_submit_directory=driver.path.parent,
        driver=driver,
        submitted_script=submitted_script,
        submitted_script_sha256=submitted_digest,
        runtime_manifest=runtime_manifest,
    )
