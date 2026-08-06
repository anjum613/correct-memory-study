from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

import pytest

from cmpilot.shared_runtime import (
    BATCH_RUNTIME_PATH_VISIBILITY_FAILURE,
    NON_SHARED_RUNTIME_PATH,
    RuntimePathError,
    classify_batch_runtime_failure,
    render_cpu_gate_wrapper,
    sha256_file,
    stage_runtime_driver,
    validate_runtime_path,
    validate_script_executables,
    validate_script_runtime_paths,
)
from cmpilot.guided_backend_cpu_job import stage_guided_backend_cpu_gate
from cmpilot.server_command_cpu_job import stage_server_command_cpu_gate


ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
HPC_SHARED_ROOT = Path("/home/s224049759")


@pytest.fixture
def shared_test_root() -> Path:
    if not HPC_SHARED_ROOT.is_dir():
        pytest.skip("HPC shared home is not present")
    directory = (
        HPC_SHARED_ROOT
        / "run-artifacts"
        / "guided-backend-shared-path"
        / f"pytest-{uuid.uuid4().hex}"
    )
    directory.mkdir(parents=True)
    try:
        yield directory
    finally:
        shutil.rmtree(directory)


@pytest.mark.parametrize("path", ["/tmp/example.py", "/var/tmp/example.py"])
def test_node_local_runtime_paths_are_rejected(path: str) -> None:
    with pytest.raises(RuntimePathError, match=NON_SHARED_RUNTIME_PATH):
        validate_runtime_path(path, shared_roots=(HPC_SHARED_ROOT,))


def test_unresolved_tmpdir_runtime_path_is_rejected() -> None:
    with pytest.raises(RuntimePathError, match=NON_SHARED_RUNTIME_PATH):
        validate_runtime_path("$TMPDIR/example.py", shared_roots=(HPC_SHARED_ROOT,))


def test_relative_runtime_path_without_shared_base_is_rejected() -> None:
    with pytest.raises(RuntimePathError, match=NON_SHARED_RUNTIME_PATH):
        validate_runtime_path("helpers/example.py", shared_roots=(HPC_SHARED_ROOT,))


def test_nonexistent_shared_runtime_path_is_rejected() -> None:
    missing = HPC_SHARED_ROOT / "run-artifacts" / "does-not-exist-cmpilot.py"
    with pytest.raises(RuntimePathError, match="does not exist"):
        validate_runtime_path(str(missing), shared_roots=(HPC_SHARED_ROOT,))


def test_unreadable_shared_runtime_path_is_rejected(shared_test_root: Path) -> None:
    helper = shared_test_root / "unreadable.py"
    helper.write_text("pass\n", encoding="utf-8")
    helper.chmod(0)
    try:
        with pytest.raises(RuntimePathError, match="not readable"):
            validate_runtime_path(str(helper), shared_roots=(shared_test_root,))
    finally:
        helper.chmod(0o600)


def test_unique_helper_beneath_hpc_home_is_accepted() -> None:
    if not HPC_SHARED_ROOT.is_dir():
        pytest.skip("HPC shared home is not present")
    directory = (
        HPC_SHARED_ROOT
        / "run-artifacts"
        / "guided-backend-shared-path"
        / f"pytest-{uuid.uuid4().hex}"
    )
    directory.mkdir(parents=True)
    helper = directory / "driver.py"
    helper.write_text("pass\n", encoding="utf-8")
    try:
        assert validate_runtime_path(
            str(helper), shared_roots=(HPC_SHARED_ROOT,)
        ) == helper.resolve()
    finally:
        shutil.rmtree(directory)


def _make_staged_shell_driver(
    tmp_path: Path, shared_test_root: Path
) -> tuple[Path, str]:
    source = tmp_path / "source-driver.sh"
    source.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'printf \'BACKEND_RAN\\n\' >"${BACKEND_MARKER:?}"\n',
        encoding="utf-8",
        newline="\n",
    )
    pre_submit = shared_test_root / "pre-submit"
    staged = stage_runtime_driver(
        source,
        pre_submit,
        shared_roots=(shared_test_root,),
        destination_name="cpu-gate-driver.sh",
    )
    return staged.path, staged.sha256


def test_generated_wrapper_verifies_driver_hash_and_copies_driver(
    tmp_path: Path, shared_test_root: Path
) -> None:
    driver, digest = _make_staged_shell_driver(tmp_path, shared_test_root)
    artifact_root = tmp_path / "artifacts"
    wrapper = render_cpu_gate_wrapper(
        driver_path=driver,
        driver_sha256=digest,
        artifact_root=artifact_root,
        driver_interpreter=Path("/usr/bin/bash"),
        shared_roots=(shared_test_root,),
    )

    assert f"EXPECTED_DRIVER_SHA256={digest}" in wrapper
    assert "/usr/bin/sha256sum -- \"$DRIVER_PATH\"" in wrapper
    assert '"$DRIVER_PATH" "$ARTIFACT_DIR/submitted-driver.sh"' in wrapper
    validate_script_runtime_paths(wrapper, shared_roots=(shared_test_root,))

    wrapper_path = shared_test_root / "pre-submit" / "gate.sbatch"
    wrapper_path.write_text(wrapper, encoding="utf-8", newline="\n")
    backend_marker = tmp_path / "backend-ran"
    environment = os.environ.copy()
    environment.update({"BACKEND_MARKER": str(backend_marker), "SLURM_JOB_ID": "12345"})
    completed = subprocess.run(
        ["/usr/bin/bash", str(wrapper_path)],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert backend_marker.read_text(encoding="utf-8") == "BACKEND_RAN\n"
    copied = artifact_root / "12345" / "submitted-driver.sh"
    assert copied.read_bytes() == driver.read_bytes()
    assert sha256_file(copied) == digest


def test_driver_hash_mismatch_fails_before_backend_checks(
    tmp_path: Path, shared_test_root: Path
) -> None:
    driver, digest = _make_staged_shell_driver(tmp_path, shared_test_root)
    artifact_root = tmp_path / "artifacts"
    wrapper = render_cpu_gate_wrapper(
        driver_path=driver,
        driver_sha256=digest,
        artifact_root=artifact_root,
        driver_interpreter=Path("/usr/bin/bash"),
        shared_roots=(shared_test_root,),
    )
    wrapper_path = shared_test_root / "pre-submit" / "gate.sbatch"
    wrapper_path.write_text(wrapper, encoding="utf-8", newline="\n")
    driver.chmod(0o600)
    driver.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    backend_marker = tmp_path / "backend-ran"
    environment = os.environ.copy()
    environment.update({"BACKEND_MARKER": str(backend_marker), "SLURM_JOB_ID": "12346"})

    completed = subprocess.run(
        ["/usr/bin/bash", str(wrapper_path)],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert completed.returncode != 0
    assert not backend_marker.exists()
    classification = json.loads(
        (artifact_root / "12346" / "classification.json").read_text(encoding="utf-8")
    )
    assert classification["label"] == "RUNTIME_SOURCE_HASH_MISMATCH"
    assert classification["backend_checks_ran"] is False


def test_generated_script_has_no_required_login_tmp_reference(
    tmp_path: Path, shared_test_root: Path
) -> None:
    driver, digest = _make_staged_shell_driver(tmp_path, shared_test_root)
    wrapper = render_cpu_gate_wrapper(
        driver_path=driver,
        driver_sha256=digest,
        artifact_root=tmp_path / "artifacts",
        driver_interpreter=Path("/usr/bin/bash"),
        shared_roots=(shared_test_root,),
    )

    marker_lines = [
        line for line in wrapper.splitlines() if "CMPILOT_REQUIRED_RUNTIME_FILE=" in line
    ]
    assert marker_lines
    assert all("/tmp/" not in line and "/var/tmp/" not in line for line in marker_lines)


def test_project_cpu_gate_generator_stages_every_runtime_path_on_shared_storage(
    shared_test_root: Path,
) -> None:
    bundle = stage_guided_backend_cpu_gate(
        project_root=ROOT,
        pre_submit_directory=shared_test_root / "pre-submit-project-gate",
        expected_environment_fingerprint="1" * 64,
        expected_content_digest="2" * 64,
        artifact_root=shared_test_root / "artifacts",
    )
    script = bundle.submitted_script.read_text(encoding="utf-8")

    assert bundle.driver.path.parent == shared_test_root / "pre-submit-project-gate"
    assert bundle.driver.sha256 == sha256_file(bundle.driver.path)
    assert bundle.submitted_script_sha256 == sha256_file(bundle.submitted_script)
    assert bundle.driver.path.stat().st_mode & 0o222 == 0
    assert bundle.submitted_script.stat().st_mode & 0o222 == 0
    assert "#SBATCH --partition=Virtual" in script
    assert "#SBATCH --cpus-per-task=2" in script
    assert "#SBATCH --mem=4G" in script
    assert "#SBATCH --time=00:20:00" in script
    assert "--expected-content-digest " + "2" * 64 in script
    assert "/tmp/" not in "\n".join(
        line for line in script.splitlines() if "CMPILOT_REQUIRED_RUNTIME_FILE=" in line
    )
    validated = validate_script_runtime_paths(script)
    assert bundle.driver.path in validated
    assert bundle.submitted_script in validated


def test_server_command_cpu_gate_is_cpu_only_and_declares_dependencies(
    shared_test_root: Path,
) -> None:
    bundle = stage_server_command_cpu_gate(
        project_root=ROOT,
        pre_submit_directory=shared_test_root / "pre-submit-command-gate",
        expected_environment_fingerprint="1" * 64,
        expected_content_digest="2" * 64,
        artifact_root=shared_test_root / "command-artifacts",
    )
    script = bundle.submitted_script.read_text(encoding="utf-8")
    manifest = json.loads(bundle.runtime_manifest.read_text(encoding="utf-8"))

    assert "#SBATCH --partition=Virtual" in script
    assert "#SBATCH --nodes=1" in script
    assert "#SBATCH --cpus-per-task=2" in script
    assert "#SBATCH --mem=4G" in script
    assert "#SBATCH --time=00:20:00" in script
    assert "#SBATCH --gres" not in script
    assert "/usr/bin/jq" not in script
    assert all(token != "jq" for line in script.splitlines() for token in line.split())
    assert bundle.driver.sha256 == sha256_file(bundle.driver.path)
    assert validate_script_executables(script)
    assert validate_script_runtime_paths(script)
    assert manifest["dependency_audit"]["jq_required"] is False
    assert manifest["schema"] == "server-command-cpu-gate-bundle-v1"


def test_executable_validator_rejects_unavailable_declared_command() -> None:
    script = "# CMPILOT_MANDATORY_EXECUTABLE=/does/not/exist/cmpilot-command\n"

    with pytest.raises(RuntimePathError, match="MISSING_MANDATORY_EXECUTABLE"):
        validate_script_executables(script)


def test_job_25264_fixture_is_path_visibility_failure_without_backend_result() -> None:
    stderr = (FIXTURES / "job_25264_slurm.stderr").read_text(encoding="utf-8")
    script = (FIXTURES / "job_25264_submitted_excerpt.sbatch").read_text(
        encoding="utf-8"
    )

    result = classify_batch_runtime_failure(stderr=stderr, stdout="", script=script)

    assert result["label"] == BATCH_RUNTIME_PATH_VISIBILITY_FAILURE
    assert result["missing_path"] == (
        "/tmp/guided-backend-fix.z67iAU/cpu-backend-gate.sbatch"
    )
    assert result["backend_checks_ran"] is False
    assert result["backend_result"] is None
    assert result["dimensions"] == {
        "environment_corruption": False,
        "gpu_failure": False,
        "guided_backend_dependency_failure": False,
        "model_failure": False,
        "vllm_failure": False,
    }
