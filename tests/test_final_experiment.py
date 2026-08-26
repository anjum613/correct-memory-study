from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from cmpilot.calculator_finalizer import FinalizerState, MANDATORY_FINALIZATION_STAGES
from cmpilot.final_experiment import (
    EXPERIMENT_SCHEMA,
    FinalExperimentError,
    aggregate_run_results,
    build_run_matrix,
    canonical_json_bytes,
    classify_run_attempts,
    load_experiment_manifest,
    validate_experiment_manifest,
    validate_run_matrix,
    write_new_canonical_json,
)


def _hash(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _revision(label: str) -> str:
    return hashlib.sha1(label.encode()).hexdigest()


def _digest(label: str) -> dict[str, str]:
    return {"path": f"frozen/{label}.json", "sha256": _hash(label)}


def _family(index: int, *, per_model: bool = False) -> dict[str, object]:
    family_id = f"family-{index + 1}"
    source_task = f"source-task-{index + 1}"
    source_revision = _revision(f"source-{index}")

    def memory(label: str, model: str | None = None) -> dict[str, object]:
        record: dict[str, object] = {
            "source_task": source_task,
            "source_repository_revision": source_revision,
            "content_sha256": _hash(f"memory-{label}-{model}"),
            "provenance_manifest_sha256": _hash(f"provenance-{label}-{model}"),
        }
        if model == "qwen":
            record.update(
                {
                    "generating_model": "Qwen/example",
                    "model_revision": _revision("qwen"),
                    "generation_seed": 100 + index,
                }
            )
        elif model == "devstral":
            record.update(
                {
                    "generating_model": "Mistral/example",
                    "model_revision": _revision("devstral"),
                    "generation_seed": 200 + index,
                }
            )
        return record

    memories: dict[str, object]
    if per_model:
        memories = {
            "SOURCE_CORRECT_MEMORY": {
                "qwen": memory("source-correct", "qwen"),
                "devstral": memory("source-correct", "devstral"),
            }
        }
    else:
        memories = {"SOURCE_CORRECT_MEMORY": memory("source-correct")}
    return {
        "family_id": family_id,
        "repository_identity": f"example/repository-{index + 1}",
        "source_task_identity": source_task,
        "target_task_identity": f"target-task-{index + 1}",
        "source_revision": source_revision,
        "target_revision": _revision(f"target-{index}"),
        "changed_trust_assumption": {
            "from": "trusted",
            "to": "requires-attestation",
        },
        "transition_type": "G6",
        "selection_provenance": _digest(f"selection-{index}"),
        "source_functionality_tests": _digest(f"source-tests-{index}"),
        "target_functionality_tests": _digest(f"target-tests-{index}"),
        "security_witness": _digest(f"witness-{index}"),
        "task_environment": _digest(f"task-environment-{index}"),
        "memories": memories,
    }


def _experiment(*, per_model: bool = False) -> dict[str, object]:
    generation_parameters = {
        "max_tokens": 512,
        "stop_tokens": [],
        "temperature": 0.0,
    }
    generation_sha256 = _hash(
        canonical_json_bytes(generation_parameters).decode("utf-8")
    )
    return {
        "schema": EXPERIMENT_SCHEMA,
        "protocol_version": "final-six-family-v1",
        "evaluator": {
            **_digest("evaluator"),
            "version": "executable-evaluator-v1",
        },
        "memory_mode": "PER_MODEL_GENERATED" if per_model else "FIXED_EXTERNAL",
        "conditions": ["NO_MEMORY", "SOURCE_CORRECT_MEMORY"],
        "repetitions": 2,
        "seeds": [104729, 130363],
        "models": {
            "qwen": {
                "model_id": "Qwen/example",
                "revision": _revision("qwen"),
                "environment_id": "qwen-frozen-v1",
                "environment_sha256": _hash("qwen-environment"),
                "profile_sha256": _hash("qwen-profile"),
                "context_limit": 4096,
                "step_limit": 100,
                "generation_parameters": generation_parameters,
                "generation_parameters_sha256": generation_sha256,
            },
            "devstral": {
                "model_id": "Mistral/example",
                "revision": _revision("devstral"),
                "environment_id": "devstral-frozen-v1",
                "environment_sha256": _hash("devstral-environment"),
                "profile_sha256": _hash("devstral-profile"),
                "context_limit": 4096,
                "step_limit": 100,
                "generation_parameters": generation_parameters,
                "generation_parameters_sha256": generation_sha256,
            },
        },
        "families": [_family(index, per_model=per_model) for index in range(6)],
    }


def _complete_attempt(path: Path, run: dict[str, object], *, witness: bool) -> None:
    path.mkdir(parents=True)
    write_new_canonical_json(path / "run-manifest.json", run)
    state = FinalizerState(
        run_id=str(run["run_id"]),
        initialized_utc="2026-08-26T00:00:00Z",
        termination_reason="NORMAL_COMPLETION",
        stage_statuses={name: "passed" for name in MANDATORY_FINALIZATION_STAGES},
        final_exit_code=0,
        final_exit_chosen_after_all_stages=True,
    )
    write_new_canonical_json(path / "finalizer-state.json", state.as_dict())
    write_new_canonical_json(
        path / "result.json",
        {
            "run_id": run["run_id"],
            "functionality_result": {"pass": True, "test_count": 7},
            "witness_result": {"pass": witness, "executable": True},
            "model_run_termination": "NORMAL_COMPLETION",
            "technical_validity": "pass",
        },
    )
    write_new_canonical_json(
        path / "classification.json",
        {"label": "OBJECTIVE_RESULT", "dimensions": {}},
    )
    for name, value in (
        ("artifact-preservation-idempotency.json", {"pass": True}),
        ("finalizer-operational-stages.json", {}),
        ("manifest-validation.json", {"pass": True}),
        ("performance-summary.json", {"available": False}),
        ("preservation-pass-1.json", {"pass_number": 1}),
        ("preservation-pass-2.json", {"pass_number": 2}),
    ):
        write_new_canonical_json(path / name, value)
    (path / "authoritative-result.txt").write_text(
        "OBJECTIVE_RESULT\n", encoding="utf-8"
    )
    (path / "sha256-manifest.txt").write_text("", encoding="utf-8")


def test_fixed_external_manifest_generates_complete_deterministic_matrix() -> None:
    experiment = _experiment()
    first = build_run_matrix(experiment)
    second = build_run_matrix(deepcopy(experiment))

    assert first == second
    assert first["run_count"] == 6 * 2 * 2 * 2
    assert len({run["run_id"] for run in first["runs"]}) == 48
    assert first["dimensions"] == {
        "families": [f"family-{index}" for index in range(1, 7)],
        "conditions": ["NO_MEMORY", "SOURCE_CORRECT_MEMORY"],
        "models": ["devstral", "qwen"],
        "repetitions": 2,
        "seeds": [104729, 130363],
    }
    assert all(
        (run["memory"] is None) == (run["condition"] == "NO_MEMORY")
        for run in first["runs"]
    )
    validate_run_matrix(first)


def test_atomic_id_changes_with_relevant_memory_or_task_hash() -> None:
    original = _experiment()
    original_matrix = build_run_matrix(original)
    changed = deepcopy(original)
    changed["families"][0]["memories"]["SOURCE_CORRECT_MEMORY"][
        "content_sha256"
    ] = _hash("changed-memory")
    changed_matrix = build_run_matrix(changed)

    before = {
        (run["family_id"], run["condition"], run["model_profile"], run["seed"]): run[
            "run_id"
        ]
        for run in original_matrix["runs"]
    }
    after = {
        (run["family_id"], run["condition"], run["model_profile"], run["seed"]): run[
            "run_id"
        ]
        for run in changed_matrix["runs"]
    }
    changed_keys = {key for key in before if before[key] != after[key]}
    assert len(changed_keys) == 4
    assert all(key[0:2] == ("family-1", "SOURCE_CORRECT_MEMORY") for key in changed_keys)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["models"]["qwen"].update(context_limit=8192),
        lambda value: value["models"]["qwen"].update(step_limit=101),
        lambda value: value["models"]["qwen"].update(
            environment_sha256=_hash("other-environment")
        ),
        lambda value: value["models"]["qwen"].update(
            profile_sha256=_hash("other-profile")
        ),
        lambda value: value["evaluator"].update(
            version="executable-evaluator-v2", sha256=_hash("evaluator-v2")
        ),
    ],
)
def test_atomic_id_binds_runtime_and_evaluator_identity(mutation) -> None:
    original = _experiment()
    changed = deepcopy(original)
    mutation(changed)
    before = build_run_matrix(original)["runs"]
    after = build_run_matrix(changed)["runs"]
    before_qwen = [run["run_id"] for run in before if run["model_profile"] == "qwen"]
    after_qwen = [run["run_id"] for run in after if run["model_profile"] == "qwen"]
    assert before_qwen != after_qwen


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value["families"].pop(), "exactly six"),
        (
            lambda value: value["families"][1].update(
                family_id=value["families"][0]["family_id"]
            ),
            "unique",
        ),
        (lambda value: value.update(conditions=["NO_MEMORY"]), "required conditions"),
        (lambda value: value.update(seeds=[1]), "one seed per repetition"),
        (
            lambda value: value["families"][0]["security_witness"].update(sha256="bad"),
            "64 lowercase",
        ),
        (
            lambda value: value["models"]["qwen"]["generation_parameters"].update(
                max_tokens=1024
            ),
            "does not match",
        ),
        (
            lambda value: value["models"]["qwen"].pop("profile_sha256"),
            "64 lowercase",
        ),
    ],
)
def test_manifest_rejects_incomplete_or_unfrozen_dimensions(mutation, message: str) -> None:
    value = _experiment()
    mutation(value)
    with pytest.raises(FinalExperimentError, match=message):
        validate_experiment_manifest(value)


def test_fixed_external_forbids_model_generation_provenance() -> None:
    value = _experiment()
    value["families"][0]["memories"]["SOURCE_CORRECT_MEMORY"][
        "generating_model"
    ] = "Qwen/example"
    with pytest.raises(FinalExperimentError, match="generation fields"):
        validate_experiment_manifest(value)


def test_per_model_memory_requires_exact_profiles_revisions_and_seeds() -> None:
    value = _experiment(per_model=True)
    validated = validate_experiment_manifest(value)
    matrix = build_run_matrix(validated)
    qwen = next(
        run
        for run in matrix["runs"]
        if run["condition"] == "SOURCE_CORRECT_MEMORY"
        and run["model_profile"] == "qwen"
    )
    devstral = next(
        run
        for run in matrix["runs"]
        if run["condition"] == "SOURCE_CORRECT_MEMORY"
        and run["model_profile"] == "devstral"
    )
    assert qwen["memory"]["generating_model"] == "Qwen/example"
    assert devstral["memory"]["generating_model"] == "Mistral/example"

    missing = deepcopy(value)
    del missing["families"][0]["memories"]["SOURCE_CORRECT_MEMORY"]["devstral"]
    with pytest.raises(FinalExperimentError, match="exactly the evaluated model keys"):
        validate_experiment_manifest(missing)
    wrong_revision = deepcopy(value)
    wrong_revision["families"][0]["memories"]["SOURCE_CORRECT_MEMORY"]["qwen"][
        "model_revision"
    ] = _revision("wrong")
    with pytest.raises(FinalExperimentError, match="revision does not match"):
        validate_experiment_manifest(wrong_revision)


def test_canonical_loader_verifies_exact_hash_and_rejects_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "experiment.json"
    expected = write_new_canonical_json(path, _experiment())
    loaded, actual = load_experiment_manifest(path, expected_sha256=expected)
    assert loaded == _experiment()
    assert actual == expected
    with pytest.raises(FinalExperimentError, match="overwrite"):
        write_new_canonical_json(path, _experiment())
    with pytest.raises(FinalExperimentError, match="hash mismatch"):
        load_experiment_manifest(path, expected_sha256="0" * 64)

    noncanonical = tmp_path / "noncanonical.json"
    noncanonical.write_text(json.dumps(_experiment()), encoding="utf-8")
    with pytest.raises(FinalExperimentError, match="not canonical"):
        load_experiment_manifest(noncanonical)


def test_matrix_validation_detects_identity_tampering() -> None:
    matrix = build_run_matrix(_experiment())
    matrix["runs"][0]["seed"] += 1
    with pytest.raises(FinalExperimentError, match="identity hash changed"):
        validate_run_matrix(matrix)


def test_resume_classification_preserves_interrupted_attempts(tmp_path: Path) -> None:
    run = build_run_matrix(_experiment())["runs"][0]
    assert classify_run_attempts(run, tmp_path)["state"] == "ABSENT"

    first = tmp_path / run["run_id"] / "attempts" / "slurm-100"
    first.mkdir(parents=True)
    write_new_canonical_json(first / "run-manifest.json", run)
    write_new_canonical_json(
        first / "finalizer-state.json",
        FinalizerState(
            run_id=str(run["run_id"]),
            initialized_utc="2026-08-26T00:00:00Z",
        ).as_dict(),
    )
    interrupted = classify_run_attempts(run, tmp_path)
    assert interrupted["state"] == "INTERRUPTED"
    assert interrupted["submission_allowed"] is True
    assert interrupted["requires_new_attempt"] is True

    second = tmp_path / run["run_id"] / "attempts" / "slurm-101"
    _complete_attempt(second, run, witness=False)
    completed = classify_run_attempts(run, tmp_path)
    assert completed["state"] == "COMPLETED"
    assert completed["completed_attempt"] == str(second)
    assert completed["submission_allowed"] is False


def test_attempt_identity_mismatch_is_not_treated_as_resumable(tmp_path: Path) -> None:
    runs = build_run_matrix(_experiment())["runs"]
    directory = tmp_path / runs[0]["run_id"]
    directory.mkdir()
    write_new_canonical_json(directory / "run-manifest.json", runs[1])
    with pytest.raises(FinalExperimentError, match="different atomic run"):
        classify_run_attempts(runs[0], tmp_path)


def test_objective_aggregation_reports_run_condition_family_and_model(tmp_path: Path) -> None:
    matrix = build_run_matrix(_experiment())
    run = matrix["runs"][0]
    _complete_attempt(tmp_path / run["run_id"], run, witness=False)

    result = aggregate_run_results(matrix, tmp_path)
    row = result["runs"][0]
    assert result["run_count"] == 48
    assert row["attempt_state"] == "COMPLETED"
    assert row["functionality_outcome"] == "PASS"
    assert row["witness_outcome"] == "FAIL"
    assert row["termination_reason"] == "NORMAL_COMPLETION"
    assert len(result["by_condition"]) == 2
    assert len(result["by_family"]) == 6
    assert len(result["by_model"]) == 2
    no_memory = next(
        group for group in result["by_condition"] if group["condition"] == "NO_MEMORY"
    )
    assert no_memory["attempt_states"] == {
        "ABSENT": 23,
        "INTERRUPTED": 0,
        "COMPLETED": 1,
    }
    assert no_memory["functionality"]["PASS"] == 1
    assert no_memory["security_witness"]["FAIL"] == 1


def test_matrix_and_aggregation_clis_are_exclusive_and_restartable(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[1]
    manifest_path = tmp_path / "experiment.json"
    matrix_path = tmp_path / "matrix.json"
    aggregation_path = tmp_path / "aggregation.json"
    run_root = tmp_path / "runs"
    manifest_sha256 = write_new_canonical_json(manifest_path, _experiment())

    generated = subprocess.run(
        (
            sys.executable,
            str(root / "scripts/generate_final_experiment_matrix.py"),
            str(manifest_path),
            str(matrix_path),
            "--expected-manifest-sha256",
            manifest_sha256,
        ),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert generated.returncode == 0, generated.stderr
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    assert matrix["run_count"] == 48
    _complete_attempt(run_root / matrix["runs"][0]["run_id"], matrix["runs"][0], witness=True)

    aggregated = subprocess.run(
        (
            sys.executable,
            str(root / "scripts/aggregate_final_experiment.py"),
            str(matrix_path),
            str(run_root),
            str(aggregation_path),
        ),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert aggregated.returncode == 0, aggregated.stderr
    aggregation = json.loads(aggregation_path.read_text(encoding="utf-8"))
    assert aggregation["run_count"] == 48
    assert aggregation["runs"][0]["witness_outcome"] == "PASS"

    duplicate = subprocess.run(
        (
            sys.executable,
            str(root / "scripts/generate_final_experiment_matrix.py"),
            str(manifest_path),
            str(matrix_path),
        ),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert duplicate.returncode == 2
    assert "refusing to overwrite" in duplicate.stderr
