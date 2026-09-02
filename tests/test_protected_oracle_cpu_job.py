from __future__ import annotations

import json
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import uuid

import pytest

from cmpilot.protected_oracle_cpu_job import (
    _snapshot_project,
    stage_protected_oracle_cpu_gate,
    validate_protected_oracle_script,
)
from scripts.protected_oracle_cpu_gate import (
    _remove_scratch_tree,
    _scratch_symlink_inventory,
    _targeted_pytest_command,
    _targeted_tests,
    build_parser,
)


ROOT = Path(__file__).parents[1]
HPC_SHARED_ROOT = Path("/home/s224049759")


def _remove_read_only_tree(root: Path) -> None:
    if not root.exists():
        return
    for path in sorted(
        root.rglob("*"), key=lambda item: len(item.parts), reverse=True
    ):
        if path.is_symlink():
            continue
        path.chmod(0o700 if path.is_dir() else 0o600)
    root.chmod(0o700)
    shutil.rmtree(root)


@pytest.fixture
def shared_test_root() -> Path:
    if not HPC_SHARED_ROOT.is_dir():
        pytest.skip("HPC shared home is not present")
    directory = (
        HPC_SHARED_ROOT
        / "run-artifacts"
        / "protected-oracle"
        / f"pytest-stage-{uuid.uuid4().hex}"
    )
    directory.mkdir(parents=True)
    try:
        yield directory
    finally:
        _remove_read_only_tree(directory)


def test_scratch_cleanup_handles_read_only_test_artifacts(tmp_path: Path) -> None:
    scratch = tmp_path / "scratch"
    nested = scratch / "readonly" / "deeper"
    nested.mkdir(parents=True)
    data = nested / "data.txt"
    data.write_text("evidence\n", encoding="utf-8")
    data.chmod(0o400)
    nested.chmod(0o500)
    nested.parent.chmod(0o500)

    _remove_scratch_tree(scratch, job_artifact_root=tmp_path)
    _remove_scratch_tree(scratch, job_artifact_root=tmp_path)

    assert not scratch.exists()


def test_protected_snapshot_excludes_transient_tmp_directory(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "tracked.py").write_text("value = 1\n", encoding="utf-8")
    transient = source / "tmp"
    transient.mkdir()
    (transient / "large-runtime.bin").write_bytes(b"not part of the snapshot")

    destination = tmp_path / "snapshot"
    manifest = _snapshot_project(source, destination)

    assert (destination / "tracked.py").is_file()
    assert not (destination / "tmp").exists()
    assert [item["path"] for item in manifest["files"]] == ["tracked.py"]


def test_scratch_cleanup_rejects_escaping_symlink_without_touching_target(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "job-artifact"
    scratch = artifact / "scratch"
    nested = scratch / "nested"
    outside = tmp_path / "outside"
    nested.mkdir(parents=True)
    outside.mkdir()
    protected = outside / "protected.txt"
    protected.write_text("must remain unchanged\n", encoding="utf-8")
    protected.chmod(0o400)
    outside.chmod(0o500)
    escaping = nested / "escaping"
    escaping.symlink_to(outside, target_is_directory=True)
    inventory = _scratch_symlink_inventory(scratch)
    assert inventory["unsafe_symlink_count"] == 1
    assert inventory["symlinks"] == [
        {
            "path": "nested/escaping",
            "target": str(outside),
            "escapes_scratch": True,
        }
    ]
    expected_file_mode = stat.S_IMODE(protected.stat().st_mode)
    expected_directory_mode = stat.S_IMODE(outside.stat().st_mode)

    try:
        with pytest.raises(RuntimeError, match="symlink escapes"):
            _remove_scratch_tree(scratch, job_artifact_root=artifact)

        assert protected.read_text(encoding="utf-8") == "must remain unchanged\n"
        assert stat.S_IMODE(protected.stat().st_mode) == expected_file_mode
        assert stat.S_IMODE(outside.stat().st_mode) == expected_directory_mode
        assert escaping.is_symlink()
    finally:
        outside.chmod(0o700)
        protected.chmod(0o600)
        if escaping.is_symlink():
            escaping.unlink()
        _remove_scratch_tree(scratch, job_artifact_root=artifact)


def test_scratch_cleanup_cannot_escape_or_touch_protected_roots(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "job-artifact"
    artifact.mkdir()
    roots = {
        name: tmp_path / name / "scratch"
        for name in (
            "source-calculator-fixture",
            "project-worktree",
            "environments",
            "model-cache",
            "historical-artifacts",
        )
    }
    expected: dict[str, tuple[bytes, int, int]] = {}
    for name, candidate in roots.items():
        candidate.mkdir(parents=True)
        marker = candidate / "marker"
        marker.write_bytes((name + "\n").encode("utf-8"))
        marker.chmod(0o400)
        candidate.chmod(0o500)
        expected[name] = (
            marker.read_bytes(),
            stat.S_IMODE(marker.stat().st_mode),
            stat.S_IMODE(candidate.stat().st_mode),
        )

    try:
        for name, candidate in roots.items():
            with pytest.raises(RuntimeError, match="exact job-owned scratch root"):
                _remove_scratch_tree(candidate, job_artifact_root=artifact)
            marker = candidate / "marker"
            contents, file_mode, directory_mode = expected[name]
            assert marker.read_bytes() == contents
            assert stat.S_IMODE(marker.stat().st_mode) == file_mode
            assert stat.S_IMODE(candidate.stat().st_mode) == directory_mode
    finally:
        for candidate in roots.values():
            candidate.chmod(0o700)
            marker = candidate / "marker"
            marker.chmod(0o600)


def test_targeted_pytest_command_contains_one_interpreter() -> None:
    interpreter = Path("/absolute/frozen/python")

    command = _targeted_pytest_command(interpreter)

    assert command == (
        str(interpreter),
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        *_targeted_tests(),
    )
    assert command.count(str(interpreter)) == 1


def test_staged_cpu_gate_has_exact_resources_and_immutable_runtime(
    shared_test_root: Path,
) -> None:
    historical = shared_test_root / "job-25575"
    cache = shared_test_root / "model-cache"
    historical.mkdir()
    cache.mkdir()
    bundle = stage_protected_oracle_cpu_gate(
        project_root=ROOT,
        pre_submit_directory=shared_test_root / "pre-submit",
        job_25575_artifacts=historical,
        model_cache_root=cache,
        expected_environment_fingerprint="1" * 64,
        expected_runtime_content_digest="2" * 64,
        expected_model_cache_digest="3" * 64,
        artifact_root=shared_test_root / "artifacts",
        cmpilot_python=Path(sys.executable),
        vllm_python=Path(sys.executable),
        shared_roots=(HPC_SHARED_ROOT,),
    )
    script = bundle.submitted_script.read_text(encoding="utf-8")

    validation = validate_protected_oracle_script(
        bundle.submitted_script,
        expected_driver_arguments=bundle.driver_arguments,
        parser=build_parser(),
    )

    assert validation["bash_syntax"] == "PASS"
    assert validation["standalone_plus_count"] == 0
    assert validation["patch_marker_count"] == 0
    assert validation["gpu_directives"] == []
    assert script.count("#SBATCH --partition=Virtual") == 1
    assert script.count("#SBATCH --nodes=1") == 1
    assert script.count("#SBATCH --cpus-per-task=2") == 1
    assert script.count("#SBATCH --mem=4G") == 1
    assert script.count("#SBATCH --time=00:30:00") == 1
    assert script.count("#SBATCH --no-requeue") == 1
    assert "#SBATCH --gres" not in script
    assert "#SBATCH --gpus" not in script
    assert stat.S_IMODE(bundle.project_snapshot.stat().st_mode) == 0o555
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o444
        for path in bundle.project_snapshot.rglob("*")
        if path.is_file()
    )
    manifest = json.loads(bundle.runtime_manifest.read_text(encoding="utf-8"))
    assert manifest["schema"] == "protected-oracle-cpu-gate-bundle-v1"
    assert manifest["script_validation"]["bash_syntax"] == "PASS"


def test_controller_finalizer_is_twice_idempotent_and_self_excluding(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    (artifact / "result.json").write_text('{"pass": true}\n', encoding="utf-8")
    pre_submit = tmp_path / "pre-submit"
    pre_submit.mkdir()
    for name in (
        "implementation.diff",
        "initial-git-state.json",
        "project-runtime-manifest.json",
        "runtime-manifest.json",
        "protected-oracle-cpu-gate.sbatch",
        "protected-oracle-cpu-gate.py",
    ):
        (pre_submit / name).write_text(f"{name}\n", encoding="utf-8")
    attestation = tmp_path / "controller-attestation"
    project_runtime = pre_submit / "project-runtime"
    project_runtime.mkdir()
    (project_runtime / "runtime.py").write_text("RUNTIME = True\n", encoding="utf-8")
    attestation.mkdir()
    (attestation / "attested-submission-result.json").write_text(
        '{"pass": true}\n', encoding="utf-8"
    )
    stdout = tmp_path / "slurm.out"
    stderr = tmp_path / "slurm.err"
    accounting = tmp_path / "sacct.txt"
    stdout.write_text("pass\n", encoding="utf-8")
    stderr.write_text("", encoding="utf-8")
    accounting.write_text("COMPLETED|0:0\n", encoding="utf-8")
    command = (
        sys.executable,
        str(ROOT / "scripts" / "finalize_protected_oracle_artifacts.py"),
        "--artifact-directory",
        str(artifact),
        "--pre-submit-directory",
        str(pre_submit),
        "--controller-attestation",
        str(attestation),
        "--slurm-stdout",
        str(stdout),
        "--slurm-stderr",
        str(stderr),
        "--slurm-accounting",
        str(accounting),
    )

    first = subprocess.run(command, text=True, capture_output=True, check=False)
    second = subprocess.run(command, text=True, capture_output=True, check=False)

    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr
    preservation = json.loads(
        (artifact / "artifact-preservation-idempotency.json").read_text()
    )
    validation = json.loads((artifact / "manifest-validation.json").read_text())
    manifest_paths = {
        line.partition("  ")[2]
        for line in (artifact / "sha256-manifest.txt").read_text().splitlines()
    }
    assert preservation["pass"] is True
    assert validation["pass"] is True
    assert validation["self_excluding"] is True
    assert "sha256-manifest.txt" not in manifest_paths
    assert (
        artifact / "pre-submit-evidence" / "project-runtime" / "runtime.py"
    ).read_bytes() == (project_runtime / "runtime.py").read_bytes()
