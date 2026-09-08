from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).parents[1]
HELPER = ROOT / "scripts/capture_gpu_diagnostic.py"


def run_helper(
    artifact_directory: Path, *, name: str, policy: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (
            sys.executable,
            str(HELPER),
            "--artifact-directory",
            str(artifact_directory),
            "--name",
            name,
            "--policy",
            policy,
            "--",
            "/usr/bin/bash",
            "-c",
            "printf diagnostic-stdout; printf diagnostic-stderr >&2; exit 7",
        ),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def load_result(artifact_directory: Path, name: str) -> dict[str, object]:
    return json.loads(
        (artifact_directory / f"{name}.result.json").read_text(encoding="utf-8")
    )


def test_nonzero_informational_diagnostic_is_preserved_without_failing_gate(
    tmp_path: Path,
) -> None:
    completed = run_helper(tmp_path, name="informational-mig", policy="informational")

    assert completed.returncode == 0, completed.stderr
    result = load_result(tmp_path, "informational-mig")
    assert result["policy"] == "informational"
    assert result["exit_code"] == 7
    assert result["diagnostic_succeeded"] is False
    assert result["batch_gate_passed"] is True
    assert result["command"] == (
        "/usr/bin/bash -c 'printf diagnostic-stdout; "
        "printf diagnostic-stderr >&2; exit 7'"
    )
    assert (tmp_path / "informational-mig.stdout").read_bytes() == b"diagnostic-stdout"
    assert (tmp_path / "informational-mig.stderr").read_bytes() == b"diagnostic-stderr"
    assert (tmp_path / "informational-mig.exit-code.txt").read_text() == "7\n"


def test_nonzero_mandatory_diagnostic_fails_gate_and_preserves_evidence(
    tmp_path: Path,
) -> None:
    completed = run_helper(tmp_path, name="mandatory-gpu", policy="mandatory")

    assert completed.returncode == 1
    result = load_result(tmp_path, "mandatory-gpu")
    assert result["policy"] == "mandatory"
    assert result["exit_code"] == 7
    assert result["diagnostic_succeeded"] is False
    assert result["batch_gate_passed"] is False
    assert (tmp_path / "mandatory-gpu.stdout").is_file()
    assert (tmp_path / "mandatory-gpu.stderr").is_file()


def test_successful_mandatory_diagnostic_passes(tmp_path: Path) -> None:
    completed = subprocess.run(
        (
            sys.executable,
            str(HELPER),
            "--artifact-directory",
            str(tmp_path),
            "--name",
            "mandatory-success",
            "--policy",
            "mandatory",
            "--",
            "/usr/bin/true",
        ),
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    result = load_result(tmp_path, "mandatory-success")
    assert result["diagnostic_succeeded"] is True
    assert result["batch_gate_passed"] is True
    assert result["exit_code"] == 0
