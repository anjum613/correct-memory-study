import json
from pathlib import Path

import pytest

from cmpilot.synthetic_memory_smoke import (
    CONDITIONS,
    OUTCOME_DIMENSIONS,
    canonical_json_bytes,
    contamination_check,
    deterministic_condition_order,
    finalize_result,
    load_json,
    memory_identity,
    prepare_run,
    prompts_equal_outside_treatment,
    render_prompt,
    split_prompt,
    tree_sha256,
)
from scripts.validate_synthetic_memory_smoke import (
    MANIFEST_PATH,
    QUALIFICATION_RESULT_PATH,
    SMOKE_ROOT,
    VALIDATION_RESULT_PATH,
    run_oracle_matrix,
    validate_manifest,
)


def test_manifest_is_canonical_complete_and_non_scientific() -> None:
    manifest = load_json(MANIFEST_PATH)

    assert MANIFEST_PATH.read_bytes() == canonical_json_bytes(manifest)
    assert validate_manifest() is True
    assert manifest["conditions"] == list(CONDITIONS)
    assert manifest["decisive_trust_condition"] == "request.peer_attested is True"
    assert manifest["scientific_evidence"] is False
    assert manifest["gpu_execution_authorized"] is False
    assert len(manifest["memory_records"]) == 3
    assert all(row["source_valid"] for row in manifest["memory_records"].values())
    assert manifest["trust_state_matrix"]["invalidated"] == {
        "faithful_reuse_functional_pass": True,
        "faithful_reuse_security_pass": False,
        "peer_attestation_guaranteed": False,
        "secure_reference_functional_pass": True,
        "secure_reference_security_pass": True,
        "source_procedure_applicable_without_guard": False,
    }


def test_frozen_assignment_and_memory_identities() -> None:
    assignment = load_json(SMOKE_ROOT / "assignment.json")

    assert assignment["execution_order"] == deterministic_condition_order(
        assignment["assignment_seed"], CONDITIONS
    )
    identities = {
        condition: memory_identity(SMOKE_ROOT, condition) for condition in CONDITIONS
    }
    assert identities["A_NO_MEMORY"]["memory_id"] is None
    assert identities["B_APPLICABLE_SOURCE_VALID"]["memory_id"] == (
        "sms-applicable-source-valid-v1"
    )
    assert identities["C_NON_APPLICABLE_SOURCE_VALID"]["memory_id"] == (
        "sms-non-applicable-source-valid-v1"
    )
    assert identities["D_ORACLE_COMPLETED"]["memory_id"] == (
        "sms-oracle-completed-v1"
    )


def test_prompts_are_identical_outside_canonical_treatment_block() -> None:
    assert prompts_equal_outside_treatment(SMOKE_ROOT) is True
    envelopes = {
        condition: split_prompt(render_prompt(SMOKE_ROOT, condition))
        for condition in CONDITIONS
    }
    assert len({value[0] for value in envelopes.values()}) == 1
    assert len({value[2] for value in envelopes.values()}) == 1
    assert "memory_id: NONE" in envelopes["A_NO_MEMORY"][1]
    assert "NO_MEMORY" in envelopes["A_NO_MEMORY"][1]
    assert "request.peer_attested is True" in envelopes["D_ORACLE_COMPLETED"][1]


def test_fresh_sessions_repositories_and_contamination_guards(tmp_path: Path) -> None:
    prepared = [
        prepare_run(SMOKE_ROOT, condition, tmp_path, f"run-{index}")
        for index, condition in enumerate(CONDITIONS)
    ]

    contamination = contamination_check(prepared)
    assert contamination["pass"] is True
    assert contamination["prompt_treatment_isolated"] is True
    assert all(row["initial_history"] == [] for row in prepared)
    source_hash = prepared[0]["repository_source_sha256"]
    assert all(row["repository_source_sha256"] == source_hash for row in prepared)
    first = Path(prepared[0]["repository_path"]) / "gateway.py"
    first.write_text("# isolated mutation\n", encoding="utf-8")
    assert all(
        tree_sha256(Path(row["repository_path"])) == source_hash
        for row in prepared[1:]
    )
    with pytest.raises(FileExistsError):
        prepare_run(SMOKE_ROOT, CONDITIONS[0], tmp_path, "run-0")


def test_independent_functional_and_security_reference_matrix() -> None:
    manifest = load_json(MANIFEST_PATH)
    assert run_oracle_matrix() == manifest["expected_reference_matrix"]


@pytest.mark.parametrize("condition", CONDITIONS)
def test_dimensional_finalizer_for_every_condition(
    tmp_path: Path, condition: str
) -> None:
    identity = memory_identity(SMOKE_ROOT, condition)
    record = {
        "condition": condition,
        "dimensions": {
            "authorized_patch_present": False,
            "completion_sentinel_emitted": False,
            "functional_oracle_pass": False,
            "prohibited_command_attempted": False,
            "prohibited_command_executed": False,
            "protected_file_integrity": True,
            "security_witness_pass": False,
            "technical_validity": True,
            "termination_reason": "CPU_SCHEMA_VALIDATION",
        },
        "memory_id": identity["memory_id"],
        "memory_provenance": identity["provenance"],
        "memory_sha256": identity["memory_sha256"],
        "run_id": f"cpu-{condition}",
        "schema": "synthetic-memory-smoke-result-v1",
        "scientific_evidence": False,
        "synthetic_validation_only": True,
    }
    output = finalize_result(tmp_path / condition, record)
    assert output.read_bytes() == canonical_json_bytes(record)
    with pytest.raises(FileExistsError):
        finalize_result(tmp_path / condition, record)


def test_result_schema_and_cpu_validation_record() -> None:
    schema = load_json(SMOKE_ROOT / "result-schema.json")
    validation = load_json(VALIDATION_RESULT_PATH)
    qualification = load_json(QUALIFICATION_RESULT_PATH)

    assert schema["dimensions"] == list(OUTCOME_DIMENSIONS)
    assert schema["scientific_evidence"] is False
    assert VALIDATION_RESULT_PATH.read_bytes() == canonical_json_bytes(validation)
    assert validation["overall"] == "PASS"
    assert all(validation["checks"].values())
    assert validation["scientific_evidence"] is False
    assert qualification["final_qualification_decision"] == "PASS"


def test_namespace_has_no_gpu_launcher_or_real_triplet() -> None:
    assert not list(SMOKE_ROOT.rglob("*.sbatch"))
    assert "synthetic" in SMOKE_ROOT.parts
    assert "real security study task" in (
        SMOKE_ROOT / "tasks/invalidated-target-task.md"
    ).read_text(encoding="utf-8")
