from __future__ import annotations

import json
from pathlib import Path
import shutil
import stat
import sys
import uuid

import pytest

from cmpilot.calculator_final_harness_cpu_job import (
    stage_calculator_final_harness_cpu_gate,
    validate_calculator_final_harness_script,
)
from scripts.calculator_final_harness_cpu_gate import (
    _targeted_pytest_command,
    _targeted_tests,
    build_parser,
)


ROOT = Path(__file__).parents[1]
SHARED = Path("/home/s224049759")


def _remove_read_only_tree(root: Path) -> None:
    if not root.exists():
        return
    for path in sorted(root.rglob("*"), key=lambda value: len(value.parts), reverse=True):
        if not path.is_symlink():
            path.chmod(0o700 if path.is_dir() else 0o600)
    root.chmod(0o700)
    shutil.rmtree(root)


@pytest.fixture
def shared_root() -> Path:
    if not SHARED.is_dir():
        pytest.skip("HPC shared storage is unavailable")
    root = (
        SHARED
        / "run-artifacts"
        / "calculator-final-harness"
        / f"pytest-stage-{uuid.uuid4().hex}"
    )
    root.mkdir(parents=True)
    try:
        yield root
    finally:
        _remove_read_only_tree(root)


def test_targeted_gate_includes_all_three_job_25642_regressions() -> None:
    tests = _targeted_tests()
    command = _targeted_pytest_command(Path("/frozen/python"))

    assert "tests/test_context_budget.py" in tests
    assert "tests/test_command_authorization.py" in tests
    assert "tests/test_source_integrity.py" in tests
    assert "tests/test_job_25642_replay.py" in tests
    assert "tests/test_calculator_task_policy_prompt.py" in tests
    assert command == (
        "/frozen/python",
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        *tests,
    )


def test_final_harness_cpu_script_is_cpu_only_attested_and_structural(
    shared_root: Path,
) -> None:
    historical = shared_root / "job-25642"
    cache = shared_root / "model-cache"
    historical.mkdir()
    cache.mkdir()
    bundle = stage_calculator_final_harness_cpu_gate(
        project_root=ROOT,
        pre_submit_directory=shared_root / "pre-submit",
        job_25642_artifacts=historical,
        model_cache_root=cache,
        expected_environment_fingerprint="1" * 64,
        expected_runtime_content_digest="2" * 64,
        expected_model_cache_digest="3" * 64,
        artifact_root=shared_root / "artifacts",
        cmpilot_python=Path(sys.executable),
        vllm_python=Path(sys.executable),
        mini_python=Path(sys.executable),
        shared_roots=(SHARED,),
    )
    script = bundle.submitted_script.read_text(encoding="utf-8")
    validation = validate_calculator_final_harness_script(
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
    manifest = json.loads(bundle.runtime_manifest.read_text(encoding="utf-8"))
    assert manifest["schema"] == "calculator-final-harness-cpu-gate-bundle-v1"
    assert manifest["script_validation"]["bash_syntax"] == "PASS"
