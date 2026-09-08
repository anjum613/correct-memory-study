from __future__ import annotations

import json
from pathlib import Path

from cmpilot.susvibes_feasibility import DEVELOPMENT_IDS


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "artifacts/context-dependent-memory-source-pairing"


def load(name: str) -> dict:
    return json.loads((ARTIFACT_ROOT / name).read_text(encoding="utf-8"))


def test_readiness_has_required_fail_closed_fields() -> None:
    value = load("readiness.json")
    required = {
        "susvibes_target_substrate_ready",
        "task_statement_cue_rule_ready",
        "development_targets",
        "source_corpus_entries",
        "source_corpus_reproducible",
        "source_correctness_validation_ready",
        "source_focal_safety_validation_ready",
        "pstar_ontology_ready",
        "oracle_firewall_status",
        "b_only_matcher_ready",
        "matcher_calibration_complete",
        "matcher_thresholds_freezeable",
        "top_one_rule_enforced",
        "pair_review_ready",
        "memory_lifecycle_ready",
        "memory_fidelity_validation_ready",
        "irrelevant_control_ready",
        "applicable_control_feasibility",
        "revalidation_intervention_ready",
        "recommended_condition_design",
        "balanced_context_ready",
        "behavior_codebook_ready",
        "development_end_to_end_pass",
        "recommended_minimum_n",
        "recommended_target_n",
        "recommended_maximum_n",
        "estimated_pair_screen_hours",
        "prospective_confirmatory_protocol_candidate_ready",
        "confirmatory_screening_authorized",
        "gpu_qualification_ready",
        "study_run_authorized",
    }
    assert required <= set(value)
    assert value["status"] == "BLOCKED"
    assert value["development_targets"] == list(DEVELOPMENT_IDS)
    assert value["susvibes_target_substrate_ready"] is True
    assert value["source_corpus_entries"] == 12
    assert value["source_corpus_reproducible"] is True
    assert value["source_correctness_validation_ready"] is True
    assert value["source_focal_safety_validation_ready"] is True
    assert value["pstar_ontology_ready"] is True
    assert value["oracle_firewall_status"] == "PASS"
    assert value["b_only_matcher_ready"] is False
    assert value["matcher_calibration_complete"] is True
    assert value["matcher_thresholds_freezeable"] is False
    assert value["top_one_rule_enforced"] is True
    assert value["pair_review_ready"] is True
    assert value["memory_lifecycle_ready"] is True
    assert value["memory_fidelity_validation_ready"] is True
    assert value["irrelevant_control_ready"] is False
    assert value["applicable_control_feasibility"] == "NOT_AVAILABLE"
    assert value["revalidation_intervention_ready"] is True
    assert value["recommended_condition_design"] == "DESIGN_C"
    assert value["balanced_context_ready"] is False
    assert value["behavior_codebook_ready"] is True
    assert value["development_end_to_end_pass"] is False
    assert value["prospective_confirmatory_protocol_candidate_ready"] is False
    assert value["confirmatory_screening_authorized"] is False
    assert value["gpu_qualification_ready"] is False
    assert value["study_run_authorized"] is False
    assert value["evaluated_model_inference_executed"] is False
    assert len(value["top_blockers"]) <= 8


def test_report_discloses_invalid_irrelevant_result_and_no_authorization() -> None:
    report = (ARTIFACT_ROOT / "development-report.md").read_text(encoding="utf-8")
    assert "Development does **not** support confirmatory screening yet" in report
    assert "src-django-signed-session-decode" in report
    assert "post-dates" in report
    assert "no rank-2/manual/postdated" in report
    assert "MATCHER_THRESHOLDS_FREEZEABLE = FALSE" in report
    assert "IRRELEVANT_CONTROL_READY = FALSE" in report
    assert "CONFIRMATORY_SCREENING_AUTHORIZED = FALSE" in report
    assert "GPU_QUALIFICATION_READY = FALSE" in report
    assert "STUDY_RUN_AUTHORIZED = FALSE" in report
    assert "No Qwen, Devstral, evaluated coding model" in report
    assert "181 unseen targets untouched" in report


def test_readiness_matches_component_artifacts() -> None:
    ready = load("readiness.json")
    assert ready["task_statement_cue_rule_ready"] == load(
        "task-statement-cue-development.json"
    )["task_statement_cue_rule_ready"]
    assert ready["source_corpus_entries"] == load("source-corpus-manifest.json")[
        "source_corpus_entries"
    ]
    assert ready["matcher_thresholds_freezeable"] == load(
        "matcher-threshold-candidate.json"
    )["matcher_thresholds_freezeable"]
    assert ready["irrelevant_control_ready"] is (
        load("irrelevant-memory-matching.json")["development_status"] == "PASS"
    )
    assert ready["development_end_to_end_pass"] == load(
        "development-end-to-end-results.json"
    )["development_end_to_end_pass"]
    assert ready["prospective_confirmatory_protocol_candidate_ready"] == load(
        "context-dependent-memory-confirmatory-v1-candidate.json"
    )["prospective_confirmatory_protocol_candidate_ready"]


def test_recorded_relevant_suite_passes_and_known_full_suite_failure_is_retained() -> None:
    tests = load("test-results.json")
    assert tests["overall"] == "PASS_RELEVANT_TESTS"
    assert tests["relevant_tests_pass"] is True
    assert tests["relevant_suite"]["classification"] == "PASS"
    assert "passed" in tests["relevant_suite"]["summary"]
    assert tests["repository_wide_suite"]["classification"] == (
        "FAIL_RECORDED_PREEXISTING_FROZEN_AIM_HASH_MISMATCH"
    )
    assert tests["repository_wide_suite"]["known_aim_hash_failure_detected"] is True
    assert tests["python_compile"]["classification"] == "PASS"
    assert tests["json_validation"]["classification"] == "PASS"
    assert tests["git_diff_check"]["classification"] == "PASS"
    assert tests["previous_tests_weakened"] is False
    assert tests["evaluated_model_endpoint_invoked"] is False
    assert tests["gpu_command_invoked"] is False
