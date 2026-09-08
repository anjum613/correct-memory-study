from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from cmpilot.experiment_models import QWEN32B_PROFILE
from cmpilot.final_experiment import build_run_matrix, write_new_canonical_json
from scripts import run_final_experiment
from tests.test_final_experiment import _experiment


def _synthetic_qwen_inputs(
    tmp_path: Path, *, step_limit: int = 15
) -> tuple[Path, str, Path, str, str]:
    manifest = deepcopy(_experiment())
    manifest["models"].pop("qwen")
    manifest["models"][QWEN32B_PROFILE.profile_id] = (
        QWEN32B_PROFILE.final_experiment_record(step_limit=step_limit)
    )
    for family in manifest["families"]:
        family["task_specification"]["runtime_backend_id"] = "synthetic-backend"
    matrix = build_run_matrix(manifest, allow_synthetic=True)
    run = next(
        row
        for row in matrix["runs"]
        if row["model_profile"] == QWEN32B_PROFILE.profile_id
    )
    manifest_path = tmp_path / "synthetic-manifest.json"
    matrix_path = tmp_path / "synthetic-matrix.json"
    manifest_sha256 = write_new_canonical_json(manifest_path, manifest)
    matrix_sha256 = write_new_canonical_json(matrix_path, matrix)
    return (
        manifest_path,
        manifest_sha256,
        matrix_path,
        matrix_sha256,
        str(run["run_id"]),
    )


def test_real_worker_preflight_is_read_only_and_fails_closed_without_bindings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, manifest_sha256, matrix, matrix_sha256, run_id = (
        _synthetic_qwen_inputs(tmp_path)
    )
    run_root = tmp_path / "runs"
    monkeypatch.setattr(run_final_experiment, "MODEL_EXECUTORS", {})
    monkeypatch.setattr(run_final_experiment, "SCIENTIFIC_BACKENDS", {})

    record, context = run_final_experiment.build_preflight(
        manifest_path=manifest,
        expected_manifest_sha256=manifest_sha256,
        matrix_path=matrix,
        expected_matrix_sha256=matrix_sha256,
        run_root=run_root,
        run_id=run_id,
        job_id="PRE_SUBMISSION",
        attempt_id="PRE_SUBMISSION",
        allow_synthetic=True,
    )

    assert context is not None
    assert record["overall"] == "FAIL"
    assert record["checks"]["frozen_inputs"] is True
    assert record["checks"]["run_identity"] is True
    assert record["checks"]["model_profile_and_executor"] is False
    assert record["checks"]["family_backend"] is False
    assert record["side_effects"] is False
    assert not run_root.exists()


def test_real_worker_preflight_passes_only_with_exact_registered_components(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, manifest_sha256, matrix, matrix_sha256, run_id = (
        _synthetic_qwen_inputs(tmp_path)
    )
    run_root = tmp_path / "runs"

    class FakeExecutor:
        def execute_agent(self, invocation: object) -> object:
            raise AssertionError("read-only preflight executed the agent")

        def shutdown(self) -> dict[str, bool]:
            return {"complete": True}

    monkeypatch.setattr(
        run_final_experiment,
        "MODEL_EXECUTORS",
        {QWEN32B_PROFILE.profile_id: lambda context: FakeExecutor()},
    )
    monkeypatch.setattr(
        run_final_experiment,
        "SCIENTIFIC_BACKENDS",
        {"synthetic-backend": object()},
    )

    record, context = run_final_experiment.build_preflight(
        manifest_path=manifest,
        expected_manifest_sha256=manifest_sha256,
        matrix_path=matrix,
        expected_matrix_sha256=matrix_sha256,
        run_root=run_root,
        run_id=run_id,
        job_id="PRE_SUBMISSION",
        attempt_id="PRE_SUBMISSION",
        allow_synthetic=True,
    )

    assert context is not None
    assert record["overall"] == "PASS"
    assert record["model_profile"] == QWEN32B_PROFILE.profile_id
    assert record["checks"] and all(record["checks"].values())
    assert record["side_effects"] is False
    assert not run_root.exists()


def test_synthetic_flag_cannot_execute_or_reserve_an_attempt(tmp_path: Path) -> None:
    manifest, manifest_sha256, matrix, matrix_sha256, run_id = (
        _synthetic_qwen_inputs(tmp_path)
    )
    run_root = tmp_path / "runs"

    with pytest.raises(
        RuntimeError, match="permitted only with --preflight-only"
    ):
        run_final_experiment.main(
            (
                "--manifest",
                str(manifest),
                "--expected-manifest-sha256",
                manifest_sha256,
                "--matrix",
                str(matrix),
                "--expected-matrix-sha256",
                matrix_sha256,
                "--run-root",
                str(run_root),
                "--run-id",
                run_id,
                "--job-id",
                "synthetic",
                "--attempt-id",
                "slurm-synthetic",
                "--allow-synthetic-diagnostic",
            )
        )
    assert not run_root.exists()


def test_qwen_step_limit_mismatch_fails_before_attempt_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, manifest_sha256, matrix, matrix_sha256, run_id = (
        _synthetic_qwen_inputs(tmp_path, step_limit=16)
    )
    run_root = tmp_path / "runs"
    monkeypatch.setattr(
        run_final_experiment,
        "SCIENTIFIC_BACKENDS",
        {"synthetic-backend": object()},
    )

    record, _ = run_final_experiment.build_preflight(
        manifest_path=manifest,
        expected_manifest_sha256=manifest_sha256,
        matrix_path=matrix,
        expected_matrix_sha256=matrix_sha256,
        run_root=run_root,
        run_id=run_id,
        job_id="PRE_SUBMISSION",
        attempt_id="PRE_SUBMISSION",
        allow_synthetic=True,
    )

    assert record["overall"] == "FAIL"
    assert record["checks"]["model_profile_and_executor"] is False
    assert "step_limit=15" in record["diagnostics"]["model_profile_and_executor"]
    assert not run_root.exists()
