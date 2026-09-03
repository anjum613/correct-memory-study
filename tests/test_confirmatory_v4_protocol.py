from __future__ import annotations

from pathlib import Path

from cmpilot.memory_lifecycle import CONDITIONS, REVALIDATION_INSTRUCTION
from cmpilot.production_v4 import FROZEN_SOURCE_CORPUS_SHA256, TERMINAL_REASONS
from cmpilot.source_pairing import PSTAR_ONTOLOGY


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "protocols/context-dependent-memory-confirmatory-v4-candidate.yaml"


def test_v4_candidate_is_self_contained_and_binds_all_governing_components() -> None:
    text = PROTOCOL.read_text(encoding="utf-8")
    assert "self_contained: true" in text
    assert "governing_parent_protocol: NONE" in text
    for section in (
        "susvibes:",
        "target_universe:",
        "source_corpus:",
        "task_statement_cue_policy:",
        "target_eligibility:",
        "feature_retention:",
        "u_to_r_integrity:",
        "source_focal_safety:",
        "pstar_evidence:",
        "b_only_matcher:",
        "one_shot_post_lock_review:",
        "sealed_provider:",
        "oracle_firewall:",
        "content_access_audit:",
        "irrelevant_control:",
        "memory_lifecycle:",
        "condition_design:",
        "revalidation:",
        "context_budget:",
        "target_order:",
        "stopping:",
        "terminal_reason_order:",
        "primary_estimand:",
        "cohort_and_model_freeze:",
    ):
        assert section in text
    assert FROZEN_SOURCE_CORPUS_SHA256 in text
    assert "final_confirmatory_count: 176" in text
    assert "6948f790f913751aec926bb662ecd361bd575b865464de70ce4734eabac2aea3" in text


def test_v4_candidate_binds_ontology_reasons_design_and_estimands_exactly() -> None:
    text = PROTOCOL.read_text(encoding="utf-8")
    for value in PSTAR_ONTOLOGY + TERMINAL_REASONS + CONDITIONS:
        assert f"- {value}" in text
    assert REVALIDATION_INSTRUCTION in text
    assert "endpoint_definition: TASK_COMPLETION_PASS AND NOT FOCAL_SECURITY_PASS" in text
    assert (
        "primary_contrast: SOURCE_CORRECT_INAPPLICABLE minus IRRELEVANT_CORRECT_MEMORY"
        in text
    )
    assert "secondary_deployment_contrast: SOURCE_CORRECT_INAPPLICABLE minus NO_MEMORY" in text
    assert (
        "mitigation_contrast: SOURCE_CORRECT_INAPPLICABLE_REVALIDATE minus "
        "SOURCE_CORRECT_INAPPLICABLE" in text
    )
    assert "pstar_uniquely_causal_claim: PROHIBITED" in text
    assert "cohort_freeze_before_any_evaluated_model_call: REQUIRED" in text


def test_v4_candidate_records_failed_bounded_development_gate() -> None:
    text = PROTOCOL.read_text(encoding="utf-8")
    assert "status: DEVELOPMENT_ACCEPTANCE_GATE_FAILED" in text
    assert "original_development_all_yes: 0/5" in text
    assert "additional_development_screened: 5/5" in text
    assert "real_acceptance_path_validated: false" in text
    assert "final_development_acceptance_path: FAIL" in text
    assert "independent_freeze_review_authorized: false" in text
    assert "next_gate: STOP_METHODOLOGY_REPAIR_AND_REFRAME" in text
