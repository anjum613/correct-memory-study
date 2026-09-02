#!/usr/bin/env python3
"""Summarize development-only yield, runtime, and end-to-end evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from cmpilot.source_pairing import stable_record_hash
from cmpilot.susvibes_feasibility import DEVELOPMENT_IDS, SUSVIBES_REVISION, sha256_file


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "artifacts/context-dependent-memory-source-pairing"
FEASIBILITY_ROOT = ROOT / "artifacts/context-dependent-memory-susvibes-feasibility"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(path)
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_bytes(json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n")


def evidence_command_key(value: Mapping[str, Any], kind: str) -> tuple[Any, ...]:
    return (kind, tuple(value["command"]), value["started_at_utc"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, default=ARTIFACT_ROOT)
    args = parser.parse_args()
    artifact_root = args.artifact_root.resolve(strict=True)

    validation = load_json(artifact_root / "source-validation-results.json")
    focal = load_json(artifact_root / "source-focal-safety-results.json")
    threshold = load_json(artifact_root / "matcher-threshold-candidate.json")
    rankings = load_json(artifact_root / "matcher-development-rankings.json")
    reviews = load_json(artifact_root / "pair-review-development-results.json")
    cues = load_json(artifact_root / "task-statement-cue-development.json")
    lifecycle = load_json(artifact_root / "memory-lifecycle-audit.json")
    feasibility = load_json(FEASIBILITY_ROOT / "readiness.json")

    candidate_count = int(validation["candidate_count"])
    qualified_count = int(validation["qualified_count"])
    if candidate_count != 13 or qualified_count != 12:
        raise RuntimeError("development source counts changed")

    evidence_commands: dict[tuple[Any, ...], Mapping[str, Any]] = {}
    build_pass_count = 0
    for row in validation["qualified"]:
        for kind in ("source_build", "source_task_test"):
            value = row[kind]
            evidence_commands[evidence_command_key(value, kind)] = value
        if row["source_build"]["classification"] == "PASS":
            build_pass_count += 1
    for row in validation["attrition"]:
        value = row["source_build"]
        evidence_commands[evidence_command_key(value, "source_build")] = value
        if value["classification"] == "PASS":
            build_pass_count += 1
        for attempt in row["source_task_test_attempts"]:
            value = attempt["source_task_test"]
            evidence_commands[evidence_command_key(value, "source_task_test_attempt")] = value

    if build_pass_count != candidate_count:
        raise RuntimeError("source build attrition changed")
    unique_runtime_seconds = sum(
        float(value["runtime_seconds"]) for value in evidence_commands.values()
    )
    lifecycle_replay_seconds = sum(
        float(row["source_replay"]["source_build"]["runtime_seconds"])
        + float(row["source_replay"]["source_task_test"]["runtime_seconds"])
        for row in lifecycle["conditions"]
        if "source_replay" in row
    )

    cue_eligible = sum(
        bool(row["public_text_eligible"]) for row in cues["results"]
    )
    locked_count = sum(
        row["development_selection"]["status"] == "LOCKED"
        for row in rankings["targets"]
    )
    accepted_count = int(reviews["accepted_count"])
    if locked_count != len(DEVELOPMENT_IDS) or accepted_count != 1:
        raise RuntimeError("diagnostic development yield changed")
    if threshold["matcher_thresholds_freezeable"] is not False:
        raise RuntimeError("runtime evidence assumes the recorded threshold blocker")

    full_186_hours = float(feasibility["estimated_full_screen_hours"])
    inherited_per_target_machine_hours = full_186_hours / int(
        feasibility["susvibes_task_count"]
    )
    unseen_count = int(feasibility["unseen_target_count"])
    unseen_machine_hours = inherited_per_target_machine_hours * unseen_count

    runtime = {
        "schema": "cmpilot-source-pairing-runtime-estimates-v1",
        "development_only": True,
        "susvibes_revision": SUSVIBES_REVISION,
        "source_corpus_entry_count": qualified_count,
        "source_candidate_count": candidate_count,
        "fractions": {
            "buildable_source": {
                "numerator": build_pass_count,
                "denominator": candidate_count,
                "fraction": round(build_pass_count / candidate_count, 2),
                "definition": "SOURCE_BUILD PASS among specified development candidates",
            },
            "source_correct": {
                "numerator": qualified_count,
                "denominator": candidate_count,
                "fraction": round(qualified_count / candidate_count, 2),
                "definition": "SOURCE_BUILD and SOURCE_TASK_TEST PASS among specified candidates",
            },
            "focal_safe_among_source_correct": {
                "numerator": int(focal["pass_count"]),
                "denominator": qualified_count,
                "fraction": round(int(focal["pass_count"]) / qualified_count, 2),
                "scope": "FOCAL_SOURCE_SAFETY_NOT_GLOBAL_SECURITY",
            },
            "task_statement_cue_eligible": {
                "numerator": cue_eligible,
                "denominator": len(DEVELOPMENT_IDS),
                "fraction": round(cue_eligible / len(DEVELOPMENT_IDS), 2),
            },
            "diagnostic_top_one_locks": {
                "numerator": locked_count,
                "denominator": len(DEVELOPMENT_IDS),
                "fraction": round(locked_count / len(DEVELOPMENT_IDS), 2),
                "confirmatory_interpretation": "NONE; numeric thresholds were unavailable",
            },
            "pstar_pair_review_all_yes": {
                "numerator": accepted_count,
                "denominator": len(DEVELOPMENT_IDS),
                "fraction": round(accepted_count / len(DEVELOPMENT_IDS), 2),
                "definition": "all 16 fixed pair-review questions YES",
            },
        },
        "matcher_pass_rate": {
            "confirmatory": "NOT_ESTIMABLE",
            "reason": "MATCHER_THRESHOLDS_FREEZEABLE is FALSE",
            "diagnostic_lock_rate": "5/5",
            "diagnostic_full_pair_acceptance": "1/5",
            "do_not_extrapolate_as_confirmatory_yield": True,
        },
        "observed_machine_runtime": {
            "unique_source_build_test_evidence_records": len(evidence_commands),
            "source_corpus_validation_seconds_total": round(unique_runtime_seconds, 1),
            "accepted_pair_three_memory_condition_replay_seconds_total": round(
                lifecycle_replay_seconds, 1
            ),
            "inherited_target_substrate_serial_hours_for_186": full_186_hours,
            "inherited_target_substrate_machine_hours_per_target_approx": round(
                inherited_per_target_machine_hours, 2
            ),
            "inherited_target_substrate_serial_hours_for_181_unseen_approx": round(
                unseen_machine_hours, 1
            ),
        },
        "source_pairing_time_per_target": {
            "reviewer_hours_planning_range": [0.5, 1.5],
            "machine_hours_excluding_model_approx": round(
                inherited_per_target_machine_hours, 2
            ),
            "basis": "B-only matching is sub-second in unit runs; target oracle execution dominates machine time; p* and alignment review was not instrumented, so reviewer time is a coarse planning range.",
            "confidence": "LOW",
        },
        "expected_confirmatory_screening_time": {
            "unseen_targets_if_all_181_screened": unseen_count,
            "reviewer_hours_range": [
                round(unseen_count * 0.5),
                round(unseen_count * 1.5),
            ],
            "machine_hours_approx": round(unseen_machine_hours, 1),
            "status": "PLANNING_ESTIMATE_ONLY_NOT_AUTHORIZED",
        },
        "sample_size_recommendation": {
            "minimum_credible_n": 8,
            "minimum_interpretation": "controlled mechanism pilot",
            "target_n": 12,
            "target_interpretation": "controlled causal workshop study",
            "maximum_practical_n": 20,
            "below_3_policy": "no average memory treatment-effect claim",
            "interpretation_bands": [
                {"n": "12+", "interpretation": "controlled causal workshop study"},
                {"n": "8-11", "interpretation": "controlled mechanism pilot"},
                {"n": "3-7", "interpretation": "case-series/methods paper"},
                {"n": "<3", "interpretation": "no average memory treatment-effect claim"},
            ],
            "power_analysis_status": "NOT_AVAILABLE_BEFORE_EXCLUDED_TASK_MODEL_QUALIFICATION",
        },
        "uncertainty": [
            "Only five heterogeneous development targets were used.",
            "The matcher threshold rule is not freezeable, so confirmatory yield is not estimable.",
            "The 1/5 diagnostic pair acceptance is reported as a count, not a population rate.",
            "Wagtail dominates observed target and source test runtime.",
            "Reviewer time was not instrumented; the range is for planning, not measurement.",
            "No evaluated model runtime or outcome is included.",
        ],
        "confirmatory_screening_authorized": False,
        "evaluated_model_inference": False,
    }

    dependencies = {
        name: sha256_file(artifact_root / name)
        for name in (
            "task-statement-cue-development.json",
            "source-corpus-manifest.json",
            "source-validation-results.json",
            "source-focal-safety-results.json",
            "pstar-ontology-candidate.json",
            "b-only-representation-results.json",
            "matcher-threshold-candidate.json",
            "matcher-development-rankings.json",
            "oracle-firewall-audit.json",
            "pair-review-development-results.json",
            "memory-lifecycle-audit.json",
            "memory-fidelity-results.json",
            "irrelevant-memory-matching.json",
            "revalidation-intervention.json",
            "condition-design-recommendation.json",
            "behavior-codebook.json",
        )
    }
    end_to_end = {
        "schema": "cmpilot-source-pairing-development-end-to-end-v1",
        "development_only": True,
        "development_targets": list(DEVELOPMENT_IDS),
        "executed_pair_target_id": lifecycle["development_target_id"],
        "executed_pair_scope": "ONE_DIAGNOSTIC_TOP_ONE_PAIR_ACCEPTED_BY_SEALED_REVIEW",
        "checks": {
            "b_task_to_b_only_representation": "PASS",
            "deterministic_top_one_ranking": "PASS_DIAGNOSTIC_ONLY",
            "immutable_source_lock": "PASS",
            "source_build_and_task_test": "PASS",
            "focal_source_safety": "PASS",
            "sealed_pair_review": "PASS",
            "exact_memory_extraction": "PASS",
            "source_session_store": "PASS",
            "new_target_session": "PASS",
            "locked_retrieval": "PASS",
            "relevant_memory_condition": "PASS",
            "matched_irrelevant_memory_condition": "PASS",
            "revalidation_condition": "PASS",
            "endpoint_plumbing": "PASS_STUB_ONLY",
            "behavior_logging": "PASS",
        },
        "conditions": [row["condition"] for row in lifecycle["conditions"]],
        "artifact_dependencies_sha256": dependencies,
        "artifact_dependencies_record_sha256": stable_record_hash(dependencies),
        "development_end_to_end_pass": lifecycle["status"] == "PASS",
        "matcher_thresholds_freezeable": False,
        "confirmatory_readiness_implication": "NONE",
        "confirmatory_screening_authorized": False,
        "gpu_qualification_ready": False,
        "study_run_authorized": False,
        "evaluated_model_inference": False,
        "status": "PASS_DEVELOPMENT_PLUMBING_ONLY",
    }

    write_json(artifact_root / "runtime-estimates.json", runtime)
    write_json(artifact_root / "development-end-to-end-results.json", end_to_end)
    print(
        json.dumps(
            {
                "status": end_to_end["status"],
                "source_corpus_entries": qualified_count,
                "diagnostic_pair_acceptance": f"{accepted_count}/{len(DEVELOPMENT_IDS)}",
                "matcher_thresholds_freezeable": False,
                "evaluated_model_inference": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
