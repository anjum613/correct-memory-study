from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import uuid

import pytest

from cmpilot.qualification_runtime_paths import (
    cleanup_runtime_directory,
    prepare_runtime_directory,
)


ROOT = Path(__file__).parents[1]
BATCH = ROOT / "slurm/qwen36_synthetic_memory_smoke.sbatch"


def _job_id() -> str:
    return f"{os.getpid()}{uuid.uuid4().int % 1_000_000:06d}"


def _runtime_path(job_id: str) -> Path:
    return Path("/tmp") / f"cmq-{job_id}"


def _write_executable(path: Path, source: str) -> Path:
    path.write_text(source, encoding="utf-8", newline="\n")
    path.chmod(0o700)
    return path


def _finalizer_functions(fake_nvidia_smi: Path) -> str:
    source = BATCH.read_text(encoding="utf-8")
    start = source.index("cleanup_server() {")
    end = source.index("trap on_exit EXIT")
    functions = source[start:end]
    assert functions.count("/usr/bin/nvidia-smi") == 1
    return functions.replace("/usr/bin/nvidia-smi", shlex.quote(str(fake_nvidia_smi)))


def _prepare_runtime(job_id: str) -> Path:
    runtime = _runtime_path(job_id)
    prepare_runtime_directory(runtime, job_id=job_id)
    (runtime / "runtime-file.txt").write_text("temporary\n", encoding="utf-8")
    return runtime


def _run_outer_finalizer(
    tmp_path: Path,
    *,
    primary_exit: int,
    runner_exit: int | None,
    signal_name: str | None = None,
    scratch: str = "present",
    port_claim: str = "present",
    partial_condition_count: int = 0,
    gpu_exit: int = 0,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    job_id = _job_id()
    runtime = _runtime_path(job_id)
    if scratch == "present":
        _prepare_runtime(job_id)
    elif scratch == "failure":
        runtime = Path("/tmp") / f"not-cmq-{job_id}"
    elif scratch != "absent":
        raise AssertionError(f"unknown scratch mode: {scratch}")

    fake_nvidia_smi = _write_executable(
        tmp_path / "fake-nvidia-smi",
        f"#!/usr/bin/bash\nprintf 'cpu-only fake nvidia-smi\\n'\nexit {gpu_exit}\n",
    )
    setup: list[str] = []
    if runner_exit is not None:
        setup.append(
            f"printf '%s\\n' {runner_exit} > "
            '"$ARTIFACT_DIR/synthetic-runner.exit"'
        )
    for ordinal in range(1, partial_condition_count + 1):
        condition = f"{ordinal:02d}-condition-{ordinal}"
        setup.extend(
            (
                f'mkdir -p "$ARTIFACT_DIR/run/conditions/{condition}"',
                f"printf '{{\"condition\": {ordinal}}}\\n' > "
                f'"$ARTIFACT_DIR/run/conditions/{condition}/result.json"',
            )
        )
    if port_claim == "present":
        setup.extend(
            (
                'PORT_LOCK_FILE="$ARTIFACT_DIR/port.lock"',
                'exec {PORT_LOCK_FD}> "$PORT_LOCK_FILE"',
                '/usr/bin/flock --exclusive --nonblock "$PORT_LOCK_FD"',
            )
        )
    elif port_claim == "failure":
        setup.extend(
            (
                'mkdir "$ARTIFACT_DIR/claim-directory"',
                'exec {PORT_LOCK_FD}> "$ARTIFACT_DIR/port-fd"',
                'PORT_LOCK_FILE="$ARTIFACT_DIR/claim-directory"',
            )
        )
    elif port_claim != "absent":
        raise AssertionError(f"unknown port-claim mode: {port_claim}")

    termination = (
        f"kill -{signal_name} \"$$\""
        if signal_name is not None
        else f"exit {primary_exit}"
    )
    script = tmp_path / "outer-finalizer-harness.sh"
    script.write_text(
        "\n".join(
            (
                "#!/usr/bin/bash",
                "set -euo pipefail",
                f"PROJECT={shlex.quote(str(ROOT))}",
                f"CMPILOT_PY={shlex.quote(sys.executable)}",
                "SERVER_LIFECYCLE_HELPER=$PROJECT/scripts/qwen36_server_lifecycle.py",
                f"ARTIFACT_DIR={shlex.quote(str(artifact))}",
                f"SLURM_JOB_ID={job_id}",
                f"RUNTIME_SCRATCH={shlex.quote(str(runtime))}",
                "PORT_LOCK_FD=",
                "PORT_LOCK_FILE=",
                "SERVER_PID=",
                _finalizer_functions(fake_nvidia_smi),
                *setup,
                "trap on_exit EXIT",
                "trap 'exit 143' TERM",
                "trap 'exit 130' INT",
                termination,
                "",
            )
        ),
        encoding="utf-8",
        newline="\n",
    )
    script.chmod(0o700)
    try:
        completed = subprocess.run(
            ["/usr/bin/bash", str(script)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    finally:
        if runtime == _runtime_path(job_id) and runtime.exists():
            cleanup_runtime_directory(runtime, job_id=job_id)
    return completed, artifact, runtime


def _load_status(artifact: Path) -> dict[str, object]:
    return json.loads((artifact / "outer-finalizer-result.json").read_text())


def _manifest_rows(artifact: Path) -> dict[str, str]:
    return {
        relative: digest
        for digest, relative in (
            line.split("  ", 1)
            for line in (artifact / "SHA256SUMS").read_text().splitlines()
        )
    }


@pytest.mark.parametrize(
    ("runner_exit", "expected_exit", "runner_success"),
    ((0, 0, True), (1, 1, False)),
)
def test_outer_finalizer_preserves_runner_exit_after_successful_cleanup(
    tmp_path: Path,
    runner_exit: int,
    expected_exit: int,
    runner_success: bool,
) -> None:
    completed, artifact, runtime = _run_outer_finalizer(
        tmp_path,
        primary_exit=runner_exit,
        runner_exit=runner_exit,
    )

    status = _load_status(artifact)
    assert completed.returncode == expected_exit, completed.stderr
    assert status["qualification_runner_exit_code"] == runner_exit
    assert status["runner_success"] is runner_success
    assert status["outer_finalizer_pass"] is True
    assert status["batch_exit_code"] == expected_exit
    assert set(status["outer_finalizer_stage_exit_codes"].values()) == {0}
    assert not runtime.exists()
    assert not (artifact / "port.lock").exists()


@pytest.mark.parametrize(
    ("signal_name", "expected_exit"), (("TERM", 143), ("INT", 130))
)
def test_outer_finalizer_runs_on_signal_without_inventing_a_runner_result(
    tmp_path: Path, signal_name: str, expected_exit: int
) -> None:
    completed, artifact, runtime = _run_outer_finalizer(
        tmp_path,
        primary_exit=0,
        runner_exit=None,
        signal_name=signal_name,
    )

    status = _load_status(artifact)
    assert completed.returncode == expected_exit, completed.stderr
    assert status["qualification_runner_exit_code"] is None
    assert status["runner_success"] is None
    assert status["outer_finalizer_pass"] is True
    assert status["batch_exit_code"] == expected_exit
    assert not runtime.exists()


def test_pre_runner_failure_finalizes_without_condition_or_runner_outcomes(
    tmp_path: Path,
) -> None:
    completed, artifact, _ = _run_outer_finalizer(
        tmp_path,
        primary_exit=7,
        runner_exit=None,
        scratch="absent",
        port_claim="absent",
    )

    status = _load_status(artifact)
    assert completed.returncode == 7
    assert status["qualification_runner_exit_code"] is None
    assert status["batch_exit_code"] == 7
    assert not (artifact / "run/conditions").exists()
    assert json.loads((artifact / "runtime-scratch-cleanup.json").read_text())[
        "already_absent"
    ] is True


def test_partial_condition_artifacts_are_preserved_and_finally_manifested(
    tmp_path: Path,
) -> None:
    completed, artifact, _ = _run_outer_finalizer(
        tmp_path,
        primary_exit=1,
        runner_exit=1,
        partial_condition_count=2,
    )

    rows = _manifest_rows(artifact)
    assert completed.returncode == 1
    assert "run/conditions/01-condition-1/result.json" in rows
    assert "run/conditions/02-condition-2/result.json" in rows
    for required in (
        "artifact-manifest.exit",
        "batch-exit-code.txt",
        "batch-primary-exit-code.txt",
        "job-finished-utc.txt",
        "outer-finalizer-result.json",
        "runtime-scratch-cleanup.json",
        "server-shutdown.exit",
        "synthetic-runner.exit",
    ):
        assert required in rows
        assert rows[required] == hashlib.sha256(
            (artifact / required).read_bytes()
        ).hexdigest()
    assert json.loads((artifact / "job-manifest.json").read_text())[
        "entry_count"
    ] == len(rows)


@pytest.mark.parametrize(
    ("primary_exit", "runner_exit", "expected_exit"),
    ((0, 0, 2), (1, 1, 1)),
)
def test_cleanup_failure_is_dimensional_and_never_masks_runner_failure(
    tmp_path: Path,
    primary_exit: int,
    runner_exit: int,
    expected_exit: int,
) -> None:
    completed, artifact, _ = _run_outer_finalizer(
        tmp_path,
        primary_exit=primary_exit,
        runner_exit=runner_exit,
        scratch="failure",
        port_claim="failure",
    )

    status = _load_status(artifact)
    stages = status["outer_finalizer_stage_exit_codes"]
    assert completed.returncode == expected_exit
    assert status["qualification_runner_exit_code"] == runner_exit
    assert status["batch_exit_code"] == expected_exit
    assert status["outer_finalizer_pass"] is False
    assert stages["port_claim_release"] == 1
    assert stages["runtime_scratch_cleanup"] == 1
    assert stages["server_shutdown"] == 0
    assert stages["artifact_manifest"] == 0


def test_cleanup_functions_are_safe_when_repeated_or_already_absent(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "artifact"
    artifact.mkdir()
    job_id = _job_id()
    runtime = _prepare_runtime(job_id)
    fake_nvidia_smi = _write_executable(
        tmp_path / "fake-nvidia-smi",
        "#!/usr/bin/bash\nexit 0\n",
    )
    script = tmp_path / "repeated-cleanup.sh"
    script.write_text(
        "\n".join(
            (
                "#!/usr/bin/bash",
                "set -euo pipefail",
                f"PROJECT={shlex.quote(str(ROOT))}",
                f"CMPILOT_PY={shlex.quote(sys.executable)}",
                "SERVER_LIFECYCLE_HELPER=$PROJECT/scripts/qwen36_server_lifecycle.py",
                f"ARTIFACT_DIR={shlex.quote(str(artifact))}",
                f"SLURM_JOB_ID={job_id}",
                f"RUNTIME_SCRATCH={shlex.quote(str(runtime))}",
                'PORT_LOCK_FILE="$ARTIFACT_DIR/port.lock"',
                'exec {PORT_LOCK_FD}> "$PORT_LOCK_FILE"',
                "SERVER_PID=",
                _finalizer_functions(fake_nvidia_smi),
                "cleanup_server",
                "cleanup_server",
                "release_port_claim",
                "release_port_claim",
                "cleanup_scratch",
                "cleanup_scratch",
                "",
            )
        ),
        encoding="utf-8",
        newline="\n",
    )
    script.chmod(0o700)
    try:
        completed = subprocess.run(
            ["/usr/bin/bash", str(script)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    finally:
        if runtime.exists():
            cleanup_runtime_directory(runtime, job_id=job_id)

    assert completed.returncode == 0, completed.stderr
    assert not runtime.exists()
    assert not (artifact / "port.lock").exists()
    assert (artifact / "server-shutdown.exit").read_text() == "0\n"
    cleanup = json.loads((artifact / "runtime-scratch-cleanup.json").read_text())
    assert cleanup["pass"] is True
    assert cleanup["already_absent"] is True
