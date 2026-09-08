from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from cmpilot.devstral_profile import DEVSTRAL_PRODUCTION_PROFILE
from cmpilot.experiment_models import QWEN32B_PROFILE
from cmpilot.final_experiment import (
    FinalExperimentError,
    canonical_json_bytes,
    reserve_run_attempt,
    sha256_bytes,
    write_new_canonical_json,
)
from cmpilot.final_submission import (
    RESOURCES,
    build_submission_plan,
    build_submission_preview,
    load_frozen_submission_inputs,
    load_submission_plan,
    render_sbatch_command,
    render_runner_preflight_commands,
    run_runner_preflights,
    select_run_id,
    submission_plan_sha256,
    validate_submission_plan,
)
from cmpilot import final_submission
from scripts import submit_final_experiment
from tests.test_final_experiment import _build, _complete_attempt, _experiment


ROOT = Path(__file__).parents[1]
BATCH = ROOT / "slurm/final_experiment_array.sbatch"


def _matrix_sha256(matrix: dict[str, object]) -> str:
    return sha256_bytes(canonical_json_bytes(matrix))


def test_model_specific_array_excludes_completed_and_restarts_interrupted(
    tmp_path: Path,
) -> None:
    matrix = _build()
    qwen_runs = [run for run in matrix["runs"] if run["model_profile"] == "qwen"]
    run_root = tmp_path / "runs"
    _complete_attempt(run_root / str(qwen_runs[0]["run_id"]), qwen_runs[0], witness=True)
    interrupted = reserve_run_attempt(
        qwen_runs[1], run_root, slurm_job_id="synthetic-old-job"
    )
    assert interrupted.is_dir()

    first = build_submission_plan(
        matrix,
        run_root,
        matrix_sha256=_matrix_sha256(matrix),
        model_profile="qwen",
        concurrency=3,
        allow_synthetic=True,
    )
    second = build_submission_plan(
        matrix,
        run_root,
        matrix_sha256=_matrix_sha256(matrix),
        model_profile="qwen",
        concurrency=3,
        allow_synthetic=True,
    )
    assert first == second
    assert first["resources"] == RESOURCES
    assert first["profile_run_count"] == 24
    assert first["completed_run_count"] == 1
    assert first["eligible_run_count"] == 23
    assert first["array_specification"] == "0-22%3"
    assert qwen_runs[0]["run_id"] not in {
        row["run_id"] for row in first["eligible_runs"]
    }
    resumed = next(
        row for row in first["eligible_runs"] if row["run_id"] == qwen_runs[1]["run_id"]
    )
    assert resumed["prior_state"] == "INTERRUPTED"
    assert resumed["attempt_mode"] == "NEW_IMMUTABLE_ATTEMPT"
    validate_submission_plan(first)


def test_production_planner_rejects_synthetic_fixture_without_diagnostic_flag(
    tmp_path: Path,
) -> None:
    matrix = _build()
    with pytest.raises(FinalExperimentError, match="PRODUCTION/FROZEN"):
        build_submission_plan(
            matrix,
            tmp_path / "runs",
            matrix_sha256=_matrix_sha256(matrix),
            model_profile="qwen",
            concurrency=1,
        )


def test_frozen_loader_rejects_synthetic_manifest_and_requires_exact_hashes(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "synthetic-manifest.json"
    matrix_path = tmp_path / "synthetic-matrix.json"
    manifest_sha256 = write_new_canonical_json(manifest_path, _experiment())
    matrix_sha256 = write_new_canonical_json(matrix_path, _build())
    with pytest.raises(FinalExperimentError, match="explicit diagnostic flag"):
        load_frozen_submission_inputs(
            manifest_path,
            matrix_path,
            expected_manifest_sha256=manifest_sha256,
            expected_matrix_sha256=matrix_sha256,
        )
    with pytest.raises(FinalExperimentError, match="hash mismatch"):
        load_frozen_submission_inputs(
            manifest_path,
            matrix_path,
            expected_manifest_sha256="0" * 64,
            expected_matrix_sha256=matrix_sha256,
            allow_synthetic=True,
        )


def test_plan_persistence_selection_and_array_command_are_exact(tmp_path: Path) -> None:
    matrix = _build()
    plan = build_submission_plan(
        matrix,
        tmp_path / "runs",
        matrix_sha256=_matrix_sha256(matrix),
        model_profile="devstral",
        concurrency=2,
        allow_synthetic=True,
    )
    plan_path = tmp_path / "submission-plan.json"
    plan_sha256 = write_new_canonical_json(plan_path, plan)
    loaded, loaded_sha256 = load_submission_plan(
        plan_path, expected_sha256=plan_sha256
    )
    assert loaded == plan
    assert loaded_sha256 == plan_sha256 == submission_plan_sha256(plan)
    assert select_run_id(
        loaded, model_profile="devstral", array_index=3
    ) == plan["eligible_runs"][3]["run_id"]
    with pytest.raises(FinalExperimentError, match="outside the frozen plan"):
        select_run_id(loaded, model_profile="devstral", array_index=24)

    command = render_sbatch_command(
        plan,
        batch_script=BATCH,
        project_root=ROOT,
        controller_python=Path(sys.executable),
        runner_script=ROOT / "scripts/run_final_experiment.py",
        manifest_path=tmp_path / "manifest.json",
        manifest_sha256=plan["experiment_manifest_sha256"],
        matrix_path=tmp_path / "matrix.json",
        plan_path=plan_path,
        plan_sha256=plan_sha256,
        log_root=tmp_path / "logs",
        begin="now+2minutes",
    )
    assert command is not None
    assert command[0] == "/slurm/bin/sbatch"
    assert "--export=NONE" in command
    assert "--array=0-23%2" in command
    assert str(BATCH) in command
    assert str(ROOT / "scripts/run_final_experiment.py") in command
    assert command[-1] == "devstral"
    preview = build_submission_preview(
        plan,
        command=command,
        batch_script=BATCH,
        plan_path=plan_path,
        manifest_path=tmp_path / "manifest.json",
        matrix_path=tmp_path / "matrix.json",
    )
    assert preview["sbatch_argv"] == list(command)
    assert preview["production_submitted"] is False
    assert preview["submission_required"] is True


def test_every_eligible_run_receives_a_preserved_read_only_runner_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    matrix = _build()
    plan = build_submission_plan(
        matrix,
        tmp_path / "runs",
        matrix_sha256=_matrix_sha256(matrix),
        model_profile="qwen",
        concurrency=2,
        allow_synthetic=True,
    )
    commands = render_runner_preflight_commands(
        plan,
        controller_python=Path(sys.executable),
        runner_script=tmp_path / "synthetic-runner.py",
        manifest_path=tmp_path / "manifest.json",
        manifest_sha256=plan["experiment_manifest_sha256"],
        matrix_path=tmp_path / "matrix.json",
    )
    observed: list[tuple[str, ...]] = []

    def fake_run(
        argv: tuple[str, ...], *, timeout: int = 60
    ) -> subprocess.CompletedProcess[bytes]:
        command = tuple(argv)
        observed.append(command)
        run_id = command[command.index("--run-id") + 1]
        result = {
            "schema": "cmpilot-final-run-preflight-v1",
            "run_id": run_id,
            "model_profile": "qwen",
            "checks": {"family_backend_registered": True},
            "overall": "PASS",
        }
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(result).encode("utf-8"),
            stderr=b"",
        )

    monkeypatch.setattr(final_submission, "_run", fake_run)
    evidence = tmp_path / "preflight-evidence"
    summary = run_runner_preflights(
        plan,
        commands=commands,
        evidence_directory=evidence,
    )
    assert summary["pass"] is True
    assert summary["run_count"] == plan["eligible_run_count"] == 24
    assert len(observed) == 24
    assert all("--preflight-only" in command for command in observed)
    assert (evidence / "summary.json").is_file()
    with pytest.raises(FinalExperimentError, match="refusing to overwrite"):
        run_runner_preflights(
            plan,
            commands=commands,
            evidence_directory=evidence,
        )


def test_any_runner_preflight_failure_blocks_the_aggregate_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    matrix = _build()
    plan = build_submission_plan(
        matrix,
        tmp_path / "runs",
        matrix_sha256=_matrix_sha256(matrix),
        model_profile="qwen",
        concurrency=1,
        allow_synthetic=True,
    )
    commands = render_runner_preflight_commands(
        plan,
        controller_python=Path(sys.executable),
        runner_script=tmp_path / "synthetic-runner.py",
        manifest_path=tmp_path / "manifest.json",
        manifest_sha256=plan["experiment_manifest_sha256"],
        matrix_path=tmp_path / "matrix.json",
    )

    def fake_run(
        argv: tuple[str, ...], *, timeout: int = 60
    ) -> subprocess.CompletedProcess[bytes]:
        command = tuple(argv)
        run_id = command[command.index("--run-id") + 1]
        failed = run_id == plan["eligible_runs"][5]["run_id"]
        result = {
            "schema": "cmpilot-final-run-preflight-v1",
            "run_id": run_id,
            "model_profile": "qwen",
            "checks": {"family_backend_registered": not failed},
            "overall": "FAIL" if failed else "PASS",
        }
        return subprocess.CompletedProcess(
            command,
            1 if failed else 0,
            stdout=json.dumps(result).encode("utf-8"),
            stderr=b"synthetic missing backend" if failed else b"",
        )

    monkeypatch.setattr(final_submission, "_run", fake_run)
    summary = run_runner_preflights(
        plan,
        commands=commands,
        evidence_directory=tmp_path / "failed-preflight",
    )
    assert summary["pass"] is False
    assert sum(row["pass"] is False for row in summary["runs"]) == 1
    assert summary["run_count"] == 24


def test_static_array_worker_fixes_cluster_resources_and_shared_runner_contract() -> None:
    text = BATCH.read_text(encoding="utf-8")
    assert text.count("#SBATCH --nodes=1") == 1
    assert text.count("#SBATCH --gres=gpu:a100:2") == 1
    assert text.count("#SBATCH --time=00:45:00") == 1
    assert "#SBATCH --no-requeue" in text
    assert "SLURM_ARRAY_TASK_ID" in text
    assert "select-run" in text
    for argument in (
        '--manifest "$MANIFEST"',
        '--expected-manifest-sha256 "$MANIFEST_SHA256"',
        '--matrix "$MATRIX"',
        '--expected-matrix-sha256 "$MATRIX_SHA256"',
        '--run-root "$RUN_ROOT"',
        '--run-id "$RUN_ID"',
        '--job-id "$SLURM_JOB_ID"',
        '--attempt-id "slurm-$SLURM_JOB_ID-$SLURM_ARRAY_TASK_ID"',
    ):
        assert argument in text
    assert "Qwen" not in text
    assert "Devstral" not in text
    assert "tensor-parallel" not in text


def test_synthetic_diagnostic_dry_run_makes_no_writes_or_scheduler_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest_path = tmp_path / "manifest.json"
    matrix_path = tmp_path / "matrix.json"
    manifest_sha256 = write_new_canonical_json(manifest_path, _experiment())
    matrix_sha256 = write_new_canonical_json(matrix_path, _build())
    runner = tmp_path / "synthetic-runner.py"
    runner.write_text("raise SystemExit('must not execute')\n", encoding="utf-8")
    plan_path = tmp_path / "outputs/submission-plan.json"
    evidence = tmp_path / "outputs/evidence"
    logs = tmp_path / "outputs/logs"

    def forbidden_submit(*args: object, **kwargs: object) -> object:
        raise AssertionError("dry-run reached the Slurm submission helper")

    monkeypatch.setattr(
        submit_final_experiment, "submit_attested_array", forbidden_submit
    )
    result = submit_final_experiment.main(
        (
            "submit",
            str(manifest_path),
            str(matrix_path),
            str(tmp_path / "runs"),
            str(plan_path),
            "--expected-manifest-sha256",
            manifest_sha256,
            "--expected-matrix-sha256",
            matrix_sha256,
            "--model-profile",
            "qwen",
            "--concurrency",
            "2",
            "--controller-python",
            sys.executable,
            "--runner-script",
            str(runner),
            "--log-root",
            str(logs),
            "--evidence-directory",
            str(evidence),
            "--allow-synthetic-diagnostic",
            "--dry-run",
        )
    )
    assert result == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["dry_run"] is True
    assert preview["production_submitted"] is False
    assert preview["plan"]["eligible_run_count"] == 24
    assert "--array=0-23%2" in preview["sbatch_argv"]
    assert preview["runner_preflight"]["status"] == "NOT_RUN"
    assert preview["runner_preflight"]["command_count"] == 24
    assert all(
        "--preflight-only" in command
        for command in preview["runner_preflight"]["commands"]
    )
    assert not plan_path.exists()
    assert not evidence.exists()
    assert not logs.exists()


def test_qualified_devstral_uses_shared_array_dry_run_without_submission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    experiment = _experiment()
    experiment["models"] = {
        QWEN32B_PROFILE.profile_id: QWEN32B_PROFILE.final_experiment_record(
            step_limit=15
        ),
        DEVSTRAL_PRODUCTION_PROFILE.profile_id: (
            DEVSTRAL_PRODUCTION_PROFILE.final_experiment_record(step_limit=15)
        ),
    }
    matrix = _build(experiment)
    manifest_path = tmp_path / "manifest.json"
    matrix_path = tmp_path / "matrix.json"
    manifest_sha256 = write_new_canonical_json(manifest_path, experiment)
    matrix_sha256 = write_new_canonical_json(matrix_path, matrix)
    runner = tmp_path / "synthetic-runner.py"
    runner.write_text("raise SystemExit('must not execute')\n", encoding="utf-8")

    monkeypatch.setattr(
        submit_final_experiment,
        "submit_attested_array",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("dry-run reached Slurm")
        ),
    )
    result = submit_final_experiment.main(
        (
            "submit",
            str(manifest_path),
            str(matrix_path),
            str(tmp_path / "runs"),
            str(tmp_path / "plan.json"),
            "--expected-manifest-sha256",
            manifest_sha256,
            "--expected-matrix-sha256",
            matrix_sha256,
            "--model-profile",
            DEVSTRAL_PRODUCTION_PROFILE.profile_id,
            "--concurrency",
            "3",
            "--controller-python",
            sys.executable,
            "--runner-script",
            str(runner),
            "--allow-synthetic-diagnostic",
            "--dry-run",
        )
    )
    preview = json.loads(capsys.readouterr().out)
    assert result == 0
    assert preview["plan"]["model_profile"] == "devstral-small-2507"
    assert preview["plan"]["resources"] == RESOURCES
    assert preview["plan"]["array_specification"] == "0-23%3"
    assert preview["sbatch_argv"][-1] == "devstral-small-2507"
    assert preview["production_submitted"] is False
