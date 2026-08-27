from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from cmpilot.calculator_finalizer import (
    FinalizerState,
    MANDATORY_FINALIZATION_STAGES,
    save_finalizer_state,
)
from cmpilot.devstral_profile import DEVSTRAL_PRODUCTION_PROFILE
from cmpilot.experiment_models import QWEN32B_PROFILE
from cmpilot.final_experiment import (
    ATTEMPT_PROVENANCE_SCHEMA,
    DEADLINE_BOUNDED_PARTIAL,
    EXACT_SIX,
    EXPERIMENT_SCHEMA,
    FROZEN,
    PRODUCTION,
    SYNTHETIC_ONLY,
    SYNTHETIC_UNIT_TEST,
    FinalExperimentError,
    aggregate_run_results,
    build_run_matrix,
    canonical_json_bytes,
    classify_run_attempts,
    load_experiment_manifest,
    reserve_run_attempt,
    resolve_final_run_context,
    validate_experiment_manifest,
    validate_run_matrix,
    validate_run_matrix_against_manifest,
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
        "tptm_provenance": _digest(f"tptm-{index}"),
        "selection_provenance": _digest(f"selection-{index}"),
        "task_specification": _digest(f"task-specification-{index}"),
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
        "purpose": SYNTHETIC_UNIT_TEST,
        "freeze_status": SYNTHETIC_ONLY,
        "protocol_version": "final-six-family-v1",
        "evaluator": {
            **_digest("evaluator"),
            "version": "executable-evaluator-v1",
        },
        "finalizer": {
            **_digest("total-finalizer"),
            "version": "total-finalizer-v1",
        },
        "memory_mode": "PER_MODEL_GENERATED" if per_model else "FIXED_EXTERNAL",
        "conditions": ["NO_MEMORY", "SOURCE_CORRECT_MEMORY"],
        "condition_definitions": {
            "NO_MEMORY": {
                **_digest("condition-no-memory"),
                "requires_memory": False,
                "treatment_type": "NO_MEMORY",
            },
            "SOURCE_CORRECT_MEMORY": {
                **_digest("condition-source-correct-memory"),
                "requires_memory": True,
                "treatment_type": "SOURCE_CORRECT_MEMORY",
            },
        },
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


def _partial_experiment(
    family_count: int,
    *,
    amendment_sha256: str = (
        "43f362095b60462731fce7519640a9a96ef14d6011062343f26b5d4d9cd6765c"
    ),
) -> dict[str, object]:
    experiment = _experiment()
    experiment["purpose"] = PRODUCTION
    experiment["freeze_status"] = FROZEN
    experiment["families"] = [
        {
            **_family(index),
            "production_admission": {
                "family_kind": "REAL_HISTORICAL",
                "path": f"families/family-{index + 1}/validation/freeze-manifest.json",
                "sha256": _hash(f"family-{index + 1}-validation"),
                "validation_status": "CPU_VALIDATION_PASS",
            },
        }
        for index in range(family_count)
    ]
    experiment["family_count_policy"] = {
        "mode": DEADLINE_BOUNDED_PARTIAL,
        "minimum": 1,
        "maximum": 3,
        "original_target": 6,
        "amendment": {
            "amendment_id": "deadline-bounded-family-count-v1",
            "path": "docs/methodology/deadline-bounded-family-count-amendment-v1.json",
            "sha256": amendment_sha256,
        },
    }
    return experiment


def _build(
    experiment: dict[str, object] | None = None,
    *,
    experiment_manifest_sha256: str | None = None,
) -> dict[str, object]:
    return build_run_matrix(
        _experiment() if experiment is None else experiment,
        experiment_manifest_sha256=experiment_manifest_sha256,
        allow_synthetic=True,
    )


def _complete_attempt(path: Path, run: dict[str, object], *, witness: bool) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if not (path / "run-manifest.json").exists():
        write_new_canonical_json(path / "run-manifest.json", run)
    if path.parent.name == "attempts" and not (
        path / "attempt-provenance.json"
    ).exists():
        job_id = path.name.removeprefix("slurm-")
        write_new_canonical_json(
            path / "attempt-provenance.json",
            {
                "schema": ATTEMPT_PROVENANCE_SCHEMA,
                "attempt_id": path.name,
                "slurm_job_id": job_id,
                "run_id": run["run_id"],
                "identity_sha256": run["identity_sha256"],
                "experiment_manifest_sha256": run[
                    "experiment_manifest_sha256"
                ],
            },
        )
    state = FinalizerState(
        run_id=str(run["run_id"]),
        initialized_utc="2026-08-26T00:00:00Z",
        termination_reason="NORMAL_COMPLETION",
        stage_statuses={name: "passed" for name in MANDATORY_FINALIZATION_STAGES},
        final_exit_code=0,
        final_exit_chosen_after_all_stages=True,
    )
    state_path = path / "finalizer-state.json"
    if state_path.exists():
        save_finalizer_state(state_path, state)
    else:
        write_new_canonical_json(state_path, state.as_dict())
    write_new_canonical_json(
        path / "result.json",
        {
            "run_id": run["run_id"],
            "identity_sha256": run["identity_sha256"],
            "experiment_manifest_sha256": run[
                "experiment_manifest_sha256"
            ],
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
    first = _build(experiment)
    second = _build(deepcopy(experiment))

    assert first == second
    assert first["run_count"] == 6 * 2 * 2 * 2
    assert len({run["run_id"] for run in first["runs"]}) == 48
    assert first["dimensions"] == {
        "families": [f"family-{index}" for index in range(1, 7)],
        "conditions": ["NO_MEMORY", "SOURCE_CORRECT_MEMORY"],
        "condition_definitions": {
            "NO_MEMORY": {
                "requires_memory": False,
                "sha256": _hash("condition-no-memory"),
            },
            "SOURCE_CORRECT_MEMORY": {
                "requires_memory": True,
                "sha256": _hash("condition-source-correct-memory"),
            },
        },
        "models": ["devstral", "qwen"],
        "repetitions": 2,
        "seeds": [104729, 130363],
    }
    assert all(
        (run["memory"] is None) == (run["condition"] == "NO_MEMORY")
        for run in first["runs"]
    )
    validate_run_matrix(first)


def test_additional_conditions_come_from_the_manifest() -> None:
    experiment = _experiment()
    extra_condition = "SYNTHETIC_ADDITIONAL_CONTROL"
    experiment["conditions"].append(extra_condition)
    experiment["condition_definitions"][extra_condition] = {
        **_digest("condition-additional-control"),
        "requires_memory": True,
        "treatment_type": "SYNTHETIC_MEMORY_CONTROL",
    }
    for index, family in enumerate(experiment["families"]):
        family["memories"][extra_condition] = {
            "source_task": family["source_task_identity"],
            "source_repository_revision": family["source_revision"],
            "content_sha256": _hash(f"extra-memory-{index}"),
            "provenance_manifest_sha256": _hash(f"extra-provenance-{index}"),
        }

    matrix = _build(experiment)

    assert matrix["dimensions"]["conditions"] == [
        "NO_MEMORY",
        "SOURCE_CORRECT_MEMORY",
        extra_condition,
    ]
    assert matrix["run_count"] == 6 * 3 * 2 * 2


def test_additional_non_memory_control_does_not_require_a_fake_memory() -> None:
    experiment = _experiment()
    extra_condition = "SYNTHETIC_NON_MEMORY_CONTROL"
    experiment["conditions"].append(extra_condition)
    experiment["condition_definitions"][extra_condition] = {
        **_digest("condition-non-memory-control"),
        "requires_memory": False,
        "treatment_type": "SYNTHETIC_PROMPT_NEUTRAL_CONTROL",
    }

    matrix = _build(experiment)

    rows = [run for run in matrix["runs"] if run["condition"] == extra_condition]
    assert len(rows) == 6 * 2 * 2
    assert all(run["memory"] is None for run in rows)
    assert all(run["condition_requires_memory"] is False for run in rows)


def test_atomic_id_changes_with_relevant_memory_or_task_hash() -> None:
    original = _experiment()
    original_matrix = _build(original)
    changed = deepcopy(original)
    changed["families"][0]["memories"]["SOURCE_CORRECT_MEMORY"][
        "content_sha256"
    ] = _hash("changed-memory")
    changed_matrix = _build(changed)

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
    # The immutable manifest digest is part of every atomic identity, so any
    # scientific-manifest change invalidates every run ID.
    assert len(changed_keys) == 48
    original_treated = next(
        run
        for run in original_matrix["runs"]
        if run["family_id"] == "family-1"
        and run["condition"] == "SOURCE_CORRECT_MEMORY"
    )
    changed_treated = next(
        run
        for run in changed_matrix["runs"]
        if run["family_id"] == "family-1"
        and run["condition"] == "SOURCE_CORRECT_MEMORY"
    )
    assert (
        original_treated["condition_record_sha256"]
        != changed_treated["condition_record_sha256"]
    )


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
        lambda value: value["finalizer"].update(
            version="total-finalizer-v2", sha256=_hash("finalizer-v2")
        ),
    ],
)
def test_atomic_id_binds_runtime_and_evaluator_identity(mutation) -> None:
    original = _experiment()
    changed = deepcopy(original)
    mutation(changed)
    before = _build(original)["runs"]
    after = _build(changed)["runs"]
    before_qwen = [run["run_id"] for run in before if run["model_profile"] == "qwen"]
    after_qwen = [run["run_id"] for run in after if run["model_profile"] == "qwen"]
    assert before_qwen != after_qwen


def test_qualified_model_profiles_share_dimensions_but_have_distinct_run_ids() -> None:
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
    rows = {
        run["model_profile"]: run
        for run in matrix["runs"]
        if run["family_id"] == "family-1"
        and run["condition"] == "NO_MEMORY"
        and run["repetition"] == 1
    }
    qwen = rows[QWEN32B_PROFILE.profile_id]
    devstral = rows[DEVSTRAL_PRODUCTION_PROFILE.profile_id]
    assert qwen["seed"] == devstral["seed"]
    assert qwen["family_id"] == devstral["family_id"]
    assert qwen["condition"] == devstral["condition"]
    assert qwen["run_id"] != devstral["run_id"]
    assert qwen["model_id"] != devstral["model_id"]
    assert qwen["model_profile_sha256"] != devstral["model_profile_sha256"]
    assert matrix["run_count"] == 6 * 2 * 2 * 2


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
        (
            lambda value: value["condition_definitions"].pop("NO_MEMORY"),
            "exactly the declared conditions",
        ),
        (
            lambda value: value["condition_definitions"]["NO_MEMORY"].update(
                requires_memory=True
            ),
            "NO_MEMORY must not require memory",
        ),
        (
            lambda value: value["condition_definitions"][
                "SOURCE_CORRECT_MEMORY"
            ].update(requires_memory=False),
            "SOURCE_CORRECT_MEMORY must require memory",
        ),
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
        (
            lambda value: value["families"][0].pop("tptm_provenance"),
            "tptm_provenance must be an object",
        ),
        (
            lambda value: value["families"][0].pop("task_specification"),
            "task_specification must be an object",
        ),
        (lambda value: value.pop("finalizer"), "finalizer must be an object"),
        (
            lambda value: value["families"][0]["memories"].update(
                UNKNOWN_CONTROL=None
            ),
            "conditions absent from the manifest",
        ),
    ],
)
def test_manifest_rejects_incomplete_or_unfrozen_dimensions(mutation, message: str) -> None:
    value = _experiment()
    mutation(value)
    with pytest.raises(FinalExperimentError, match=message):
        validate_experiment_manifest(value, allow_synthetic=True)


def test_manifest_purpose_and_freeze_are_fail_closed() -> None:
    synthetic = _experiment()
    with pytest.raises(FinalExperimentError, match="explicit diagnostic flag"):
        validate_experiment_manifest(synthetic)

    malformed_production = deepcopy(synthetic)
    malformed_production["purpose"] = PRODUCTION
    malformed_production["freeze_status"] = "NOT_FROZEN"
    with pytest.raises(FinalExperimentError, match="freeze_status=FROZEN"):
        validate_experiment_manifest(malformed_production)

    wrong_synthetic_status = deepcopy(synthetic)
    wrong_synthetic_status["freeze_status"] = FROZEN
    with pytest.raises(FinalExperimentError, match="freeze_status=SYNTHETIC_ONLY"):
        validate_experiment_manifest(
            wrong_synthetic_status, allow_synthetic=True
        )


def test_existing_manifest_retains_exact_six_default() -> None:
    experiment = _experiment()
    validated = validate_experiment_manifest(experiment, allow_synthetic=True)
    assert "family_count_policy" not in validated

    matrix = _build(experiment)
    assert matrix["family_count_policy"] == {"mode": EXACT_SIX}
    assert matrix["achieved_family_count"] == 6
    assert matrix["achieved_trust_category_coverage"] == ["G6"]

    explicit = deepcopy(experiment)
    explicit["family_count_policy"] = {"mode": EXACT_SIX}
    validate_experiment_manifest(explicit, allow_synthetic=True)


@pytest.mark.parametrize("family_count", [1, 2, 3])
def test_deadline_bounded_partial_accepts_one_to_three_real_families(
    family_count: int,
) -> None:
    experiment = _partial_experiment(family_count)
    validated = validate_experiment_manifest(experiment)
    assert len(validated["families"]) == family_count
    assert validated["family_count_policy"]["original_target"] == 6


@pytest.mark.parametrize("family_count", [0, 4])
def test_deadline_bounded_partial_rejects_counts_outside_one_to_three(
    family_count: int,
) -> None:
    with pytest.raises(FinalExperimentError, match="requires 1 to 3"):
        validate_experiment_manifest(_partial_experiment(family_count))


def test_partial_production_without_explicit_amendment_is_rejected() -> None:
    experiment = _partial_experiment(1)
    experiment.pop("family_count_policy")
    with pytest.raises(FinalExperimentError, match="exactly six"):
        validate_experiment_manifest(experiment)


def test_synthetic_family_cannot_satisfy_partial_production_count() -> None:
    experiment = _partial_experiment(1)
    experiment["families"][0].pop("production_admission")
    with pytest.raises(FinalExperimentError, match="production_admission"):
        validate_experiment_manifest(experiment)

    synthetic = _partial_experiment(1)
    synthetic["purpose"] = SYNTHETIC_UNIT_TEST
    synthetic["freeze_status"] = SYNTHETIC_ONLY
    with pytest.raises(FinalExperimentError, match="only for a PRODUCTION"):
        validate_experiment_manifest(synthetic, allow_synthetic=True)


def test_partial_matrix_cardinality_remains_the_cartesian_product() -> None:
    matrix = build_run_matrix(_partial_experiment(1))
    assert matrix["run_count"] == 1 * 2 * 2 * 2
    assert matrix["achieved_family_count"] == 1
    assert matrix["family_count_policy"]["mode"] == DEADLINE_BOUNDED_PARTIAL
    assert matrix["achieved_trust_category_coverage"] == ["G6"]


def test_amendment_hash_changes_manifest_and_atomic_run_identity() -> None:
    first = build_run_matrix(_partial_experiment(1, amendment_sha256="1" * 64))
    second = build_run_matrix(_partial_experiment(1, amendment_sha256="2" * 64))
    assert first["experiment_manifest_sha256"] != second[
        "experiment_manifest_sha256"
    ]
    assert [run["run_id"] for run in first["runs"]] != [
        run["run_id"] for run in second["runs"]
    ]


def test_amendment_methodology_record_is_canonical_and_hash_frozen() -> None:
    path = (
        Path(__file__).parents[1]
        / "docs/methodology/deadline-bounded-family-count-amendment-v1.json"
    )
    payload = path.read_bytes()
    assert payload == canonical_json_bytes(json.loads(payload))
    assert hashlib.sha256(payload).hexdigest() == (
        "43f362095b60462731fce7519640a9a96ef14d6011062343f26b5d4d9cd6765c"
    )


def test_fixed_external_forbids_model_generation_provenance() -> None:
    value = _experiment()
    value["families"][0]["memories"]["SOURCE_CORRECT_MEMORY"][
        "generating_model"
    ] = "Qwen/example"
    with pytest.raises(FinalExperimentError, match="generation fields"):
        validate_experiment_manifest(value, allow_synthetic=True)


def test_per_model_memory_requires_exact_profiles_revisions_and_seeds() -> None:
    value = _experiment(per_model=True)
    validated = validate_experiment_manifest(value, allow_synthetic=True)
    matrix = _build(validated)
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
        validate_experiment_manifest(missing, allow_synthetic=True)
    wrong_revision = deepcopy(value)
    wrong_revision["families"][0]["memories"]["SOURCE_CORRECT_MEMORY"]["qwen"][
        "model_revision"
    ] = _revision("wrong")
    with pytest.raises(FinalExperimentError, match="revision does not match"):
        validate_experiment_manifest(wrong_revision, allow_synthetic=True)


def test_canonical_loader_verifies_exact_hash_and_rejects_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "experiment.json"
    expected = write_new_canonical_json(path, _experiment())
    loaded, actual = load_experiment_manifest(
        path, expected_sha256=expected, allow_synthetic=True
    )
    assert loaded == _experiment()
    assert actual == expected
    with pytest.raises(FinalExperimentError, match="overwrite"):
        write_new_canonical_json(path, _experiment())
    with pytest.raises(FinalExperimentError, match="hash mismatch"):
        load_experiment_manifest(
            path, expected_sha256="0" * 64, allow_synthetic=True
        )

    noncanonical = tmp_path / "noncanonical.json"
    noncanonical.write_text(json.dumps(_experiment()), encoding="utf-8")
    with pytest.raises(FinalExperimentError, match="not canonical"):
        load_experiment_manifest(noncanonical, allow_synthetic=True)


def test_matrix_validation_detects_identity_tampering() -> None:
    matrix = _build()
    matrix["runs"][0]["seed"] += 1
    with pytest.raises(FinalExperimentError, match="identity hash changed"):
        validate_run_matrix(matrix)


def test_matrix_generation_rejects_an_unrelated_supplied_manifest_hash() -> None:
    with pytest.raises(FinalExperimentError, match="canonical manifest"):
        _build(experiment_manifest_sha256="0" * 64)


def test_matrix_validation_requires_complete_canonical_cartesian_order() -> None:
    reordered = _build()
    reordered["runs"][0], reordered["runs"][1] = (
        reordered["runs"][1],
        reordered["runs"][0],
    )
    reordered_ids = [run["run_id"] for run in reordered["runs"]]
    reordered["run_ids_sha256"] = hashlib.sha256(
        canonical_json_bytes(reordered_ids)
    ).hexdigest()
    with pytest.raises(FinalExperimentError, match="canonical Cartesian ordering"):
        validate_run_matrix(reordered)

    truncated = _build()
    truncated["runs"].pop()
    truncated["run_count"] = len(truncated["runs"])
    truncated["run_ids_sha256"] = hashlib.sha256(
        canonical_json_bytes([run["run_id"] for run in truncated["runs"]])
    ).hexdigest()
    with pytest.raises(FinalExperimentError, match="complete Cartesian product"):
        validate_run_matrix(truncated)

    wrong_seed_schedule = _build()
    wrong_seed_schedule["dimensions"]["seeds"].reverse()
    with pytest.raises(FinalExperimentError, match="seed assignment"):
        validate_run_matrix(wrong_seed_schedule)

    unsafe_no_memory = _build()
    unsafe_no_memory["dimensions"]["condition_definitions"]["NO_MEMORY"][
        "requires_memory"
    ] = True
    with pytest.raises(FinalExperimentError, match="NO_MEMORY must not require memory"):
        validate_run_matrix(unsafe_no_memory)


def test_matrix_validation_rejects_copied_memory_tampering() -> None:
    matrix = _build()
    treated = next(
        run for run in matrix["runs"] if run["condition"] != "NO_MEMORY"
    )
    treated["memory"]["content_sha256"] = _hash("tampered-memory-copy")
    with pytest.raises(FinalExperimentError, match="memory content hash changed"):
        validate_run_matrix(matrix)


def test_matrix_must_be_the_exact_expansion_of_its_manifest() -> None:
    experiment = _experiment()
    matrix = _build(experiment)
    assert (
        validate_run_matrix_against_manifest(
            matrix, experiment, allow_synthetic=True
        )
        == matrix
    )

    changed = deepcopy(experiment)
    changed["families"][0]["repository_identity"] = "example/other-repository"
    with pytest.raises(FinalExperimentError, match="exact expansion"):
        validate_run_matrix_against_manifest(
            matrix, changed, allow_synthetic=True
        )


def test_shared_context_keeps_treatment_out_of_the_model_adapter() -> None:
    experiment = _experiment()
    run = next(
        item
        for item in _build(experiment)["runs"]
        if item["condition"] == "SOURCE_CORRECT_MEMORY"
    )
    context = resolve_final_run_context(
        experiment, run, allow_synthetic=True
    )

    assert context["family_manifest"]["family_id"] == run["family_id"]
    assert context["condition"] == run["condition"]
    assert context["seed"] == run["seed"]
    assert context["run_identity"]["schema"].endswith("identity-v2")
    assert context["treatment"]["memory"] == run["memory"]
    assert context["treatment"]["condition_definition"] == experiment[
        "condition_definitions"
    ][run["condition"]]
    assert "memory" not in context["model_profile"]

    tampered = deepcopy(run)
    tampered["memory"]["content_sha256"] = _hash("tampered-context-memory")
    with pytest.raises(FinalExperimentError, match="exact atomic record"):
        resolve_final_run_context(
            experiment, tampered, allow_synthetic=True
        )


def test_resume_classification_preserves_interrupted_attempts(tmp_path: Path) -> None:
    run = _build()["runs"][0]
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


def test_attempt_reservation_is_immutable_and_refuses_completed_runs(
    tmp_path: Path,
) -> None:
    run = _build()["runs"][0]
    attempt = reserve_run_attempt(run, tmp_path, slurm_job_id="28493_7")

    assert attempt.name == "slurm-28493_7"
    provenance = json.loads(
        (attempt / "attempt-provenance.json").read_text(encoding="utf-8")
    )
    assert provenance["slurm_job_id"] == "28493_7"
    assert provenance["run_id"] == run["run_id"]
    interrupted = classify_run_attempts(run, tmp_path)
    assert interrupted["state"] == "INTERRUPTED"
    assert interrupted["attempts"][0]["slurm_job_id"] == "28493_7"

    with pytest.raises(FinalExperimentError, match="reuse immutable attempt"):
        reserve_run_attempt(run, tmp_path, slurm_job_id="28493_7")

    _complete_attempt(attempt, run, witness=True)
    assert classify_run_attempts(run, tmp_path)["state"] == "COMPLETED"
    with pytest.raises(FinalExperimentError, match="rerun completed"):
        reserve_run_attempt(run, tmp_path, slurm_job_id="28494")


def test_attempt_reservation_accepts_only_job_bound_array_attempt_ids(
    tmp_path: Path,
) -> None:
    run = _build()["runs"][1]
    with pytest.raises(FinalExperimentError, match="slurm-<job_id>"):
        reserve_run_attempt(
            run,
            tmp_path,
            slurm_job_id="28500",
            attempt_id="slurm-99999-4",
        )

    attempt = reserve_run_attempt(
        run,
        tmp_path,
        slurm_job_id="28500",
        attempt_id="slurm-28500-4",
    )
    provenance = json.loads(
        (attempt / "attempt-provenance.json").read_text(encoding="utf-8")
    )
    assert attempt.name == "slurm-28500-4"
    assert provenance["attempt_id"] == "slurm-28500-4"
    assert provenance["slurm_job_id"] == "28500"


def test_attempt_identity_mismatch_is_not_treated_as_resumable(tmp_path: Path) -> None:
    runs = _build()["runs"]
    directory = tmp_path / runs[0]["run_id"]
    directory.mkdir()
    write_new_canonical_json(directory / "run-manifest.json", runs[1])
    with pytest.raises(FinalExperimentError, match="different atomic run"):
        classify_run_attempts(runs[0], tmp_path)


def test_objective_aggregation_reports_run_condition_family_and_model(tmp_path: Path) -> None:
    matrix = _build()
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
            "--synthetic-unit-test",
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
    assert aggregation["runs"][0]["security_witness_outcome"] == "PASS"

    duplicate = subprocess.run(
        (
            sys.executable,
            str(root / "scripts/generate_final_experiment_matrix.py"),
            str(manifest_path),
            str(matrix_path),
            "--synthetic-unit-test",
        ),
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert duplicate.returncode == 2
    assert "refusing to overwrite" in duplicate.stderr


def test_matrix_cli_rejects_synthetic_input_without_diagnostic_flag(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[1]
    manifest_path = tmp_path / "synthetic-experiment.json"
    matrix_path = tmp_path / "matrix.json"
    manifest_sha256 = write_new_canonical_json(manifest_path, _experiment())

    rejected = subprocess.run(
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
    assert rejected.returncode == 2
    assert "explicit diagnostic flag" in rejected.stderr
    assert not matrix_path.exists()


def test_matrix_cli_requires_expected_hash_for_production_mode(
    tmp_path: Path,
) -> None:
    root = Path(__file__).parents[1]
    manifest_path = tmp_path / "synthetic-experiment.json"
    matrix_path = tmp_path / "matrix.json"
    write_new_canonical_json(manifest_path, _experiment())

    rejected = subprocess.run(
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
    assert rejected.returncode == 2
    assert "production generation requires --expected-manifest-sha256" in rejected.stderr
    assert not matrix_path.exists()
