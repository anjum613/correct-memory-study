from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "artifacts/context-dependent-memory-source-pairing-v2"


def _readiness() -> dict:
    return json.loads((ARTIFACT_ROOT / "readiness.json").read_text(encoding="utf-8"))


def test_readiness_has_all_required_decision_fields() -> None:
    value = _readiness()
    required = {
        "parent_development_protocol_commit",
        "successor_protocol_commit",
        "successor_protocol_frozen_before_new_evidence",
        "source_corpus_entries",
        "source_corpus_reproducible",
        "source_correct_count",
        "source_focal_safe_count",
        "source_only_partition_used",
        "matcher_design",
        "global_similarity_threshold_required",
        "b_only_matcher_ready",
        "ambiguity_policy_ready",
        "top_one_rule_enforced",
        "no_rank2_fallback",
        "development_pairs_reviewed_v2",
        "development_all_yes_pairs_v2",
        "irrelevant_control_ready",
        "irrelevant_control_timestamp_valid",
        "irrelevant_control_matching_rule",
        "memory_lifecycle_ready",
        "memory_fidelity_ready",
        "revalidation_ready",
        "recommended_condition_design",
        "design_c_end_to_end_pass",
        "prospective_confirmatory_v2_candidate_ready",
        "recommended_minimum_n",
        "recommended_target_n",
        "recommended_maximum_n",
        "estimated_confirmatory_screen_hours",
        "confirmatory_screening_authorized",
        "gpu_qualification_ready",
        "study_run_authorized",
    }
    assert required <= set(value)


def test_readiness_reports_success_without_authorizing_execution() -> None:
    value = _readiness()
    assert value["development_v2_success"] is True
    assert value["source_corpus_entries"] == 50
    assert value["source_correct_count"] == 50
    assert value["source_focal_safe_count"] == 50
    assert value["global_similarity_threshold_required"] is False
    assert value["b_only_matcher_ready"] is True
    assert value["ambiguity_policy_ready"] is True
    assert value["top_one_rule_enforced"] is True
    assert value["no_rank2_fallback"] is True
    assert value["irrelevant_control_ready"] is True
    assert value["irrelevant_control_timestamp_valid"] is True
    assert value["design_c_end_to_end_pass"] is True
    assert value["prospective_confirmatory_v2_candidate_ready"] is True
    assert value["confirmatory_screening_authorized"] is False
    assert value["gpu_qualification_ready"] is False
    assert value["study_run_authorized"] is False


def test_report_and_minimum_artifact_set_are_present() -> None:
    required = {
        "development-v2-report.md",
        "readiness.json",
        "successor-protocol.md",
        "successor-protocol.json",
        "source-universe-design.json",
        "expanded-source-corpus-manifest.json",
        "source-validation-summary.json",
        "matcher-v2-design.json",
        "matcher-v2-development-rankings.json",
        "ambiguity-policy.json",
        "pair-review-v2-development-results.json",
        "irrelevant-control-v2.json",
        "packet-length-analysis.json",
        "design-c-end-to-end.json",
        "runtime-estimates.json",
        "context-dependent-memory-confirmatory-v2-candidate.md",
        "context-dependent-memory-confirmatory-v2-candidate.json",
    }
    assert required <= {path.name for path in ARTIFACT_ROOT.iterdir() if path.is_file()}
    report = (ARTIFACT_ROOT / "development-v2-report.md").read_text(encoding="utf-8")
    assert "Development V2 succeeds" in report
    assert "confirmatory_screening_authorized = FALSE" in report
    assert "No evaluated-model behavior" in report


def test_n_recommendation_comes_from_runtime_artifact() -> None:
    ready = _readiness()
    runtime = json.loads((ARTIFACT_ROOT / "runtime-estimates.json").read_text())
    recommendation = runtime["sample_size_recommendation"]
    assert ready["recommended_minimum_n"] == recommendation["recommended_minimum_n"]
    assert ready["recommended_target_n"] == recommendation["recommended_target_n"]
    assert ready["recommended_maximum_n"] == recommendation["recommended_maximum_n"]
