from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import paper.human_verification as human_verification
from paper.validate_evidence import (
    validate_bibliography,
    validate_claim_ledger,
    validate_controls,
    validate_external_audit_tables,
    validate_human_review_packets,
    validate_identification_contract,
    validate_manuscript_claim_language,
    validate_no_scientific_mutation,
    validate_tex_sources,
    validate_v1_evidence,
    validate_v4_attrition,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _mutate_loaded_yaml(
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    original_load = human_verification._load_yaml
    target = (REPOSITORY_ROOT / relative).resolve()

    def load_with_mutation(path: Path) -> dict[str, Any]:
        document = original_load(path)
        if path.resolve() == target:
            mutation(document)
        return document

    monkeypatch.setattr(human_verification, "_load_yaml", load_with_mutation)


def test_frozen_claim_ledger_and_v1_table() -> None:
    validate_claim_ledger()
    validate_v1_evidence()


def test_estimand_derived_contract_and_v4_attrition() -> None:
    validate_identification_contract()
    validate_v4_attrition()


def test_positive_and_negative_controls_match_frozen_evidence() -> None:
    validate_controls()


def test_external_tables_and_human_packets_match_frozen_ratings() -> None:
    validate_external_audit_tables()
    validate_human_review_packets()


def test_manuscript_claim_boundaries_and_bibliography() -> None:
    validate_manuscript_claim_language()
    validate_bibliography()
    validate_tex_sources()


def test_no_scientific_artifact_was_changed() -> None:
    validate_no_scientific_mutation()


def test_human_protocol_was_frozen_before_blank_responses() -> None:
    state = human_verification.validate_human_verification(REPOSITORY_ROOT)

    assert state["PROTOCOL_FREEZE_COMMIT"] == (
        human_verification.PROTOCOL_FREEZE_COMMIT
    )
    assert state["PROTOCOL_COMMITTED_BEFORE_HUMAN_RESPONSES"] is True
    assert state["PACKETS"] == 6
    assert state["TOTAL_PRIORITY_CELLS"] == 23
    assert state["AI_DISAGREEMENT_CELLS"] == 17
    assert state["SAMPLED_AI_AGREEMENT_CELLS"] == 6
    assert state["SAMPLE_RULE_VERIFIED"] is True
    assert state["HUMAN_CELLS_COMPLETED"] == 0
    assert state["HUMAN_RESPONSES_CURRENTLY_BLANK"] is True
    assert state["HUMAN_VERIFICATION_COMPLETED"] is False
    assert state["ORIGINAL_AI_AUDIT_PRESERVED"] is True
    assert state["ORIGINAL_CLAIM_LEDGER_PRESERVED"] is True
    assert state["ORIGINAL_POSITIVE_CONTROL_PRESERVED"] is True
    assert state["ORIGINAL_V4_EVIDENCE_PRESERVED"] is True
    assert state["POST_REVIEW_OVERLAY_READY"] is True
    assert state["HUMAN_RESPONSE_OPTIONS"] == [
        "AGREE",
        "DISAGREE",
        "CANNOT_DETERMINE",
    ]
    assert state["EVALUATED_MODEL_RUNS"] == 0
    assert state["GPU_USE"] == 0
    assert state["UNSEEN_CONFIRMATORY_TARGETS_SCREENED"] == 0
    assert state["NEW_REAL_TARGETS_SCREENED"] == 0
    assert state["NEW_EXTERNAL_AUDIT_PAPERS"] == 0


def test_human_validation_rejects_changed_sampling_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def change_sample(document: dict[str, Any]) -> None:
        document["SELECTED"][0]["CRITERION"] = "A2_INSECURE_TASK_COMPLETING_CONTROL"

    _mutate_loaded_yaml(
        monkeypatch,
        "paper/human-review/sampling-rule.yaml",
        change_sample,
    )
    with pytest.raises(
        human_verification.HumanVerificationError,
        match="agreement sampling rule changed",
    ):
        human_verification.validate_human_verification(REPOSITORY_ROOT)


def test_human_validation_rejects_nonpriority_substitution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def substitute_nonpriority(document: dict[str, Any]) -> None:
        cell = next(
            cell
            for cell in document["CRITERIA"]
            if not cell["PRIORITY_HUMAN_VERIFICATION"]
        )
        cell["PRIORITY_HUMAN_VERIFICATION"] = True

    _mutate_loaded_yaml(
        monkeypatch,
        "paper/human-review/01-basm-when-not-to-imitate.yaml",
        substitute_nonpriority,
    )
    with pytest.raises(
        human_verification.HumanVerificationError,
        match="nonpriority cell substituted or priority flag changed",
    ):
        human_verification.validate_human_verification(REPOSITORY_ROOT)


def test_human_validation_rejects_overwritten_ai_adjudication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def overwrite_ai_rating(document: dict[str, Any]) -> None:
        document["CRITERIA"][0]["ADJUDICATED_RATING"] = "ESTABLISHED"

    _mutate_loaded_yaml(
        monkeypatch,
        "paper/human-review/01-basm-when-not-to-imitate.yaml",
        overwrite_ai_rating,
    )
    with pytest.raises(
        human_verification.HumanVerificationError,
        match="AI-adjudicated rating overwritten",
    ):
        human_verification.validate_human_verification(REPOSITORY_ROOT)


def test_human_validation_rejects_changed_criterion_definition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def overwrite_criterion(document: dict[str, Any]) -> None:
        document["CRITERIA"][0]["FROZEN_CRITERION_TEXT"] = "changed"

    _mutate_loaded_yaml(
        monkeypatch,
        "paper/human-review/01-basm-when-not-to-imitate.yaml",
        overwrite_criterion,
    )
    with pytest.raises(
        human_verification.HumanVerificationError,
        match="criterion definition changed in packet",
    ):
        human_verification.validate_human_verification(REPOSITORY_ROOT)


def test_human_validation_rejects_completion_with_blank_priority_cells(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def mark_complete(document: dict[str, Any]) -> None:
        document["HUMAN_VERIFICATION_COMPLETED"] = True

    _mutate_loaded_yaml(
        monkeypatch,
        "paper/human-review/reconciliation.yaml",
        mark_complete,
    )
    with pytest.raises(
        human_verification.HumanVerificationError,
        match="while priority cells remain blank",
    ):
        human_verification.validate_human_verification(REPOSITORY_ROOT)


def test_disagreement_requires_rationale_and_original_evidence() -> None:
    valid_response = {
        "REVIEWER_ID_OR_PSEUDONYM": "reviewer-1",
        "HUMAN_RESPONSE": "DISAGREE",
        "HUMAN_PREFERRED_STATUS": "ESTABLISHED",
        "HUMAN_RATIONALE": "Concise evidence-rating rationale.",
        "HUMAN_ORIGINAL_SOURCE_EVIDENCE_LOCATION": "Official paper, section 1.",
        "CORRECTION_BASIS": "EVIDENCE_RATING_CORRECTION",
    }
    for field, message in (
        ("HUMAN_RATIONALE", "lacks rationale"),
        ("HUMAN_ORIGINAL_SOURCE_EVIDENCE_LOCATION", "lacks original-source evidence"),
    ):
        invalid_response = {**valid_response, field: ""}
        with pytest.raises(human_verification.HumanVerificationError, match=message):
            human_verification.validate_response_record(
                invalid_response,
                ai_adjudicated_status="NOT_ESTABLISHED",
                location="PAPER/CRITERION",
            )


def test_overlay_writer_cannot_target_original_ai_audit() -> None:
    audit_path = (
        REPOSITORY_ROOT
        / "audits/external-identification-v1/papers/01-basm-when-not-to-imitate.yaml"
    )
    before = audit_path.read_bytes()

    with pytest.raises(
        human_verification.HumanVerificationError,
        match="overlay output must be",
    ):
        human_verification.write_human_verified_overlay(
            audit_path,
            REPOSITORY_ROOT,
        )

    assert audit_path.read_bytes() == before


def test_overlay_cannot_be_built_from_blank_packets() -> None:
    with pytest.raises(
        human_verification.HumanVerificationError,
        match="before all 23 cells are complete",
    ):
        human_verification.build_human_verified_overlay(REPOSITORY_ROOT)
