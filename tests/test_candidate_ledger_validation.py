from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts/validate-candidate-ledger.py"
SCHEMA = ROOT / "benchmark-selection/candidate.schema.json"
PROTOCOL_VERSION = "benchmark-selection-v0.1"
SHA256 = "a" * 64


def _load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("candidate_ledger_validator", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = _load_validator()


def _artifact(name: str) -> dict[str, str]:
    return {"path": f"evidence/{name}.json", "sha256": SHA256}


def _status_history(*states: str) -> list[dict[str, object]]:
    return [
        {
            "sequence": sequence,
            "state": state,
            "recorded_at_utc": f"2026-08-13T00:{sequence:02d}:00Z",
            "actor_id": "selector-01",
            "protocol_version": PROTOCOL_VERSION,
            "rationale": f"Recorded {state}",
            "evidence": [],
        }
        for sequence, state in enumerate(states, start=1)
    ]


def _definition(name: str) -> dict[str, str]:
    return {
        "description": f"Controlled {name} definition",
        "definition_path": f"triplet/{name}.json",
        "definition_sha256": SHA256,
    }


def _implementation(name: str, witness: str) -> dict[str, object]:
    return {
        "artifact_path": f"triplet/{name}.patch",
        "artifact_sha256": SHA256,
        "functional_pass": True,
        "security_witness": witness,
    }


def _instrument(name: str, **extra: object) -> dict[str, object]:
    return {
        "artifact_path": f"triplet/{name}.py",
        "artifact_sha256": SHA256,
        "deterministic": True,
        **extra,
    }


def _selected_candidate(candidate_id: str = "CMVP-CAND-0001") -> dict[str, object]:
    states = (
        "DISCOVERED",
        "AUTOMATIC_GATES_PASSED",
        "MECHANISM_REVIEW_PASSED",
        "TRIPLET_VALIDATED",
        "INDEPENDENT_REVIEW_APPROVED",
        "ELIGIBLE",
        "SELECTED",
    )
    hard_gates = {
        gate: {"status": "PASS", "evidence": [_artifact(gate)]}
        for gate in VALIDATOR.HARD_GATES
    }
    return {
        "candidate_id": candidate_id,
        "protocol_version": PROTOCOL_VERSION,
        "current_state": "SELECTED",
        "status_history": _status_history(*states),
        "source": {
            "forge": "example-forge",
            "repository_url": "https://example.invalid/owner/repository",
            "upstream_owner": "owner",
            "upstream_name": "repository",
            "licence_spdx": "MIT",
            "discovery": {
                "source_list_id": "discovery-v1",
                "source_list_sha256": SHA256,
                "position": 1,
                "discovered_at_utc": "2026-08-13T00:00:00Z",
                "discoverer_id": "discoverer-01",
            },
            "snapshot": {
                "commit_sha": "b" * 40,
                "commit_date_utc": "2026-08-12T00:00:00Z",
                "tree_sha256": SHA256,
                "metadata_sha256": SHA256,
                "retrieval_method": "documented archive retrieval",
            },
        },
        "trust_family": "TRUSTED_DATA_BECOMES_ATTACKER_INFLUENCED",
        "mechanism_key": "example-mechanism",
        "hard_gates": hard_gates,
        "mechanism_card": _artifact("mechanism-card"),
        "triplet": {
            "source_task": _definition("source-task"),
            "compatible_target": _definition("compatible-target"),
            "invalidated_target": _definition("invalidated-target"),
            "p_star": {
                "statement": "One narrow decisive trust condition",
                "observation_path": "triplet/p-star-observation.json",
                "observation_sha256": SHA256,
            },
            "faithful_reuse": _implementation("faithful-reuse", "OPEN"),
            "secure_reference": _implementation("secure-reference", "BLOCKED"),
            "functional_oracle": _instrument(
                "functional-oracle", implementation_independent=True
            ),
            "security_witness": _instrument("security-witness"),
        },
        "independent_review": {
            "reviewer_id": "reviewer-01",
            "constructor_id": "constructor-01",
            "outcome_blind": True,
            "conflict_free": True,
            "decision": "APPROVE",
            "reviewed_at_utc": "2026-08-13T01:00:00Z",
            "artifact_path": "reviews/CMVP-CAND-0001.json",
            "artifact_sha256": SHA256,
        },
        "scoring": {
            "rubric_version": "benchmark-selection-scoring-rubric-v0.1",
            "dimension_scores": {
                "construction_parsimony": 3,
                "decisive_condition_observability": 3,
                "oracle_diagnostic_precision": 3,
                "reproducibility_margin": 3,
                "ecological_grounding": 3,
            },
            "total": 15,
            "tie_break_digest": hashlib.sha256(
                (
                    f"{PROTOCOL_VERSION}|{VALIDATOR.SELECTION_SEED}|{candidate_id}"
                ).encode("utf-8")
            ).hexdigest(),
        },
        "treatment_results_consulted": False,
    }


def _freeze(candidate: dict[str, object]) -> None:
    history = candidate["status_history"]
    assert isinstance(history, list)
    history.append(
        _status_history("FROZEN")[0]
        | {
            "sequence": len(history) + 1,
            "recorded_at_utc": "2026-08-13T01:30:00Z",
        }
    )
    candidate["current_state"] = "FROZEN"
    candidate["benchmark_freeze"] = {
        "freeze_id": "cmvp-benchmark-v1",
        "frozen_at_utc": "2026-08-13T02:00:00Z",
        "protocol_version": PROTOCOL_VERSION,
        "artifact_hashes": {
            "candidate_ledger": SHA256,
            "selection_protocol": SHA256,
        },
        "treatment_results_absent_certification": {
            "certified": True,
            "certifier_id": "freeze-reviewer-01",
            "certified_at_utc": "2026-08-13T02:00:00Z",
            "evidence_sha256": SHA256,
        },
    }


def _validate(tmp_path: Path, *records: object) -> dict[str, object]:
    ledger = tmp_path / "candidate-ledger.jsonl"
    ledger.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    return VALIDATOR.validate_ledger(ledger, schema=SCHEMA)


def _codes(result: dict[str, object]) -> set[str]:
    errors = result["errors"]
    assert isinstance(errors, list)
    return {error["code"] for error in errors}


def test_schema_records_protocol_states_gates_and_trust_strata() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["protocol_version"]["const"] == PROTOCOL_VERSION
    assert set(schema["$defs"]["state"]["enum"]) == set(VALIDATOR.STATES)
    assert set(schema["$defs"]["hard_gates"]["required"]) == set(
        VALIDATOR.HARD_GATES
    )
    assert set(schema["$defs"]["trust_family"]["enum"]) == set(
        VALIDATOR.TRUST_FAMILIES
    )


def test_empty_initial_ledger_is_valid(tmp_path: Path) -> None:
    assert _validate(tmp_path)["pass"] is True


def test_complete_selected_and_frozen_candidates_are_valid(tmp_path: Path) -> None:
    selected = _selected_candidate()
    frozen = _selected_candidate("CMVP-CAND-0002")
    frozen["source"]["upstream_name"] = "repository-two"  # type: ignore[index]
    frozen["source"]["repository_url"] = (  # type: ignore[index]
        "https://example.invalid/owner/repository-two"
    )
    _freeze(frozen)

    result = _validate(tmp_path, selected, frozen)

    assert result["pass"] is True
    assert result["record_count"] == 2


def test_missing_required_identifier_is_rejected(tmp_path: Path) -> None:
    candidate = _selected_candidate()
    del candidate["source"]["snapshot"]["commit_sha"]  # type: ignore[index]

    assert "MISSING_REQUIRED_IDENTIFIER" in _codes(_validate(tmp_path, candidate))


def test_invalid_state_transition_is_rejected(tmp_path: Path) -> None:
    candidate = _selected_candidate()
    candidate["status_history"] = _status_history("DISCOVERED", "SELECTED")

    assert "INVALID_STATE_TRANSITION" in _codes(_validate(tmp_path, candidate))


def test_accepted_candidate_with_failed_hard_gate_is_rejected(
    tmp_path: Path,
) -> None:
    candidate = _selected_candidate()
    candidate["hard_gates"]["usable_licence"]["status"] = "FAIL"  # type: ignore[index]

    assert "ACCEPTED_WITH_FAILED_HARD_GATE" in _codes(
        _validate(tmp_path, candidate)
    )


def test_excluded_candidate_without_reason_is_rejected(tmp_path: Path) -> None:
    candidate = _selected_candidate()
    candidate["current_state"] = "EXCLUDED"
    candidate["status_history"] = _status_history("DISCOVERED", "EXCLUDED")

    assert "MISSING_EXCLUSION_REASON" in _codes(_validate(tmp_path, candidate))


def test_selected_candidate_without_independent_review_is_rejected(
    tmp_path: Path,
) -> None:
    candidate = _selected_candidate()
    del candidate["independent_review"]

    assert "SELECTED_WITHOUT_INDEPENDENT_REVIEW" in _codes(
        _validate(tmp_path, candidate)
    )


@pytest.mark.parametrize(
    "definition",
    ["source_task", "compatible_target", "invalidated_target", "p_star"],
)
def test_selected_candidate_requires_complete_triplet_definitions(
    tmp_path: Path, definition: str
) -> None:
    candidate = _selected_candidate()
    candidate["triplet"][definition] = {}  # type: ignore[index]

    assert "SELECTED_WITHOUT_TRIPLET_DEFINITIONS" in _codes(
        _validate(tmp_path, candidate)
    )


@pytest.mark.parametrize(
    "component",
    ["faithful_reuse", "secure_reference", "functional_oracle", "security_witness"],
)
def test_selected_candidate_requires_complete_validation_components(
    tmp_path: Path, component: str
) -> None:
    candidate = _selected_candidate()
    candidate["triplet"][component] = {}  # type: ignore[index]

    assert "SELECTED_WITHOUT_VALIDATION_COMPONENTS" in _codes(
        _validate(tmp_path, candidate)
    )


def test_faithful_and_secure_reference_witness_directions_are_enforced(
    tmp_path: Path,
) -> None:
    candidate = _selected_candidate()
    candidate["triplet"]["faithful_reuse"]["security_witness"] = "BLOCKED"  # type: ignore[index]
    candidate["triplet"]["secure_reference"]["security_witness"] = "OPEN"  # type: ignore[index]

    assert "SELECTED_WITHOUT_VALIDATION_COMPONENTS" in _codes(
        _validate(tmp_path, candidate)
    )


def test_treatment_outcomes_before_freeze_are_rejected(tmp_path: Path) -> None:
    candidate = _selected_candidate()
    candidate["treatment_outcomes"] = {"treatment": "unsafe patch"}

    assert "TREATMENT_OUTCOME_BEFORE_BENCHMARK_FREEZE" in _codes(
        _validate(tmp_path, candidate)
    )


def test_missing_protocol_version_is_rejected(tmp_path: Path) -> None:
    candidate = _selected_candidate()
    del candidate["protocol_version"]

    assert "MISSING_PROTOCOL_VERSION" in _codes(_validate(tmp_path, candidate))


def test_duplicate_candidate_ids_are_rejected(tmp_path: Path) -> None:
    candidate = _selected_candidate()

    assert "DUPLICATE_CANDIDATE_ID" in _codes(
        _validate(tmp_path, candidate, deepcopy(candidate))
    )


def test_malformed_status_history_is_rejected(tmp_path: Path) -> None:
    candidate = _selected_candidate()
    candidate["status_history"][0]["sequence"] = 9  # type: ignore[index]

    assert "MALFORMED_STATUS_HISTORY" in _codes(_validate(tmp_path, candidate))


def test_nonchronological_status_history_is_rejected(tmp_path: Path) -> None:
    candidate = _selected_candidate()
    candidate["status_history"][2]["recorded_at_utc"] = (  # type: ignore[index]
        "2026-08-12T23:59:00Z"
    )

    assert "MALFORMED_STATUS_HISTORY" in _codes(_validate(tmp_path, candidate))


def test_frozen_candidate_without_artifact_hashes_is_rejected(tmp_path: Path) -> None:
    candidate = _selected_candidate()
    _freeze(candidate)
    candidate["benchmark_freeze"]["artifact_hashes"] = {}  # type: ignore[index]

    assert "MISSING_ARTIFACT_HASHES_AT_FREEZE" in _codes(
        _validate(tmp_path, candidate)
    )


@pytest.mark.parametrize(
    "criterion",
    [
        "expected_treatment_effect",
        "expected_memory_following",
        "memory_completeness",
        "apparent_support_for_hypothesis",
    ],
)
def test_outcome_related_scoring_criteria_are_rejected(
    tmp_path: Path, criterion: str
) -> None:
    candidate = _selected_candidate()
    candidate["scoring"]["dimension_scores"][criterion] = 3  # type: ignore[index]

    assert "FORBIDDEN_SCORING_CRITERION" in _codes(
        _validate(tmp_path, candidate)
    )


def test_selected_candidate_requires_complete_seeded_scoring(tmp_path: Path) -> None:
    candidate = _selected_candidate()
    candidate["scoring"]["total"] = 14  # type: ignore[index]
    candidate["scoring"]["tie_break_digest"] = SHA256  # type: ignore[index]

    assert "MALFORMED_POST_GATE_SCORING" in _codes(
        _validate(tmp_path, candidate)
    )


def test_selected_set_enforces_repository_cap(tmp_path: Path) -> None:
    first = _selected_candidate()
    second = _selected_candidate("CMVP-CAND-0002")

    assert "REPOSITORY_CAP_EXCEEDED" in _codes(_validate(tmp_path, first, second))


def test_selected_set_enforces_mechanism_cap(tmp_path: Path) -> None:
    candidates = [
        _selected_candidate(f"CMVP-CAND-{index:04d}") for index in range(1, 4)
    ]
    for index, candidate in enumerate(candidates, start=1):
        source = candidate["source"]
        assert isinstance(source, dict)
        source["upstream_name"] = f"repository-{index}"
        source["repository_url"] = (
            f"https://example.invalid/owner/repository-{index}"
        )

    assert "MECHANISM_CAP_EXCEEDED" in _codes(_validate(tmp_path, *candidates))
