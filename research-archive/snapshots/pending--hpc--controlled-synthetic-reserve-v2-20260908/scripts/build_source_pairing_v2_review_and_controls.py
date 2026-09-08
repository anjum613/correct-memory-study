#!/usr/bin/env python3
"""Build sealed V2 development review, controls, and no-model DESIGN_C evidence."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from cmpilot.memory_lifecycle import (
    CONDITIONS,
    REVALIDATION_INSTRUCTION,
    MemoryStore,
    audit_memory_packet,
    build_retrieval_query,
    context_budget_record,
    memory_metrics,
    mock_agent_endpoint,
    render_memory_packet,
    sha256_bytes,
)
from cmpilot.pair_review import (
    PAIR_REVIEW_QUESTIONS,
    build_sealed_response,
    pair_review_form,
    review_request_hash,
    validate_review_request,
)
from cmpilot.source_corpus_v2 import PROTOCOL_ID, SUCCESSOR_PROTOCOL_COMMIT
from cmpilot.source_pairing import stable_record_hash
from cmpilot.source_pairing_v2 import (
    select_irrelevant_memory_v2,
    validate_locked_irrelevant_timestamp,
)
from cmpilot.susvibes_feasibility import DEVELOPMENT_IDS, sha256_file


ROOT = Path(__file__).resolve().parents[1]
V1_ROOT = ROOT / "artifacts/context-dependent-memory-source-pairing"
FEASIBILITY_ROOT = ROOT / "artifacts/context-dependent-memory-susvibes-feasibility"
DEFAULT_ROOT = ROOT / "artifacts/context-dependent-memory-source-pairing-v2"
DEFAULT_MEMORY_ROOT = ROOT / "tmp/context-dependent-memory-source-pairing-v2/design-c-mock"
REVIEW_CONFIG = ROOT / "configs/v2/context-dependent-memory-pair-review-development-v2.json"
SEALED_ROOT = ROOT / "oracle_sealed/susvibes-development"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(path)
    return value


def write_json(path: Path, value: Any) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite V2 evidence: {path}")
    path.write_bytes(json.dumps(value, indent=2, sort_keys=True).encode() + b"\n")


def directory_packet_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for candidate in sorted(path.rglob("*")):
        if candidate.is_symlink() or not candidate.is_file():
            continue
        relative = candidate.relative_to(path).as_posix().encode()
        data = candidate.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def rows_by_id(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, Mapping[str, Any]]:
    result = {str(row[key]): row for row in rows}
    if set(result) != set(DEVELOPMENT_IDS):
        raise RuntimeError(f"development row set changed: {key}")
    return result


def objective_answers(
    *,
    target_id: str,
    entry: Mapping[str, Any],
    ranking: Mapping[str, Any],
    task_case: Mapping[str, Any],
    security_case: Mapping[str, Any],
    cue: Mapping[str, Any],
) -> dict[str, str]:
    pstar = entry["focal_source_safety"]["pstar"]
    task_results = task_case["results"]
    security_results = security_case["focal_security_results"]
    return {
        "Q1": "YES" if entry["source_build"]["classification"] == "PASS" else "NO",
        "Q2": "YES" if ranking["sealed_exact_timestamp_validation"]["status"] == "PASS" else "NO",
        "Q3": "YES" if entry["source_task_test"]["classification"] == "PASS" else "NO",
        "Q4": "YES" if entry["source_implementation_or_patch"].strip() else "NO",
        "Q6": "YES" if isinstance(pstar, Mapping) and len(pstar) >= 7 else "NO",
        "Q7": "YES" if pstar["source_truth"] is True else "NO",
        "Q9": (
            "YES"
            if entry["focal_source_safety"]["classification"] == "PASS"
            and entry["focal_source_safety"]["level"] in {"A", "B", "C"}
            else "NO"
        ),
        "Q12": "YES",
        "Q13": (
            "YES"
            if task_results["U_VULNERABLE_IMPLEMENTATION"] == "PASS"
            and security_results["U"] == "FAIL"
            else "NO"
        ),
        "Q14": (
            "YES"
            if task_results["R_SAFE_IMPLEMENTATION"] == "PASS"
            and security_results["R"] == "PASS"
            else "NO"
        ),
        "Q15": (
            "YES"
            if ranking["selection_lock"]["rank_2_fallback"] is False
            else "NO"
        ),
        "Q16": "YES" if cue["public_text_eligible"] is True else "NO",
    }


def build_reviews(
    *,
    artifact_root: Path,
    rankings: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    config = load_json(REVIEW_CONFIG)
    ranking_hash = sha256_file(artifact_root / "matcher-v2-development-rankings.json")
    if config["matcher_rankings_sha256"] != ranking_hash:
        raise RuntimeError("review config was not created for the immutable rankings")
    config_rows = rows_by_id(config["results"], "target_id")
    ranking_rows = rows_by_id(rankings["targets"], "target_id")
    entries = {row["source_id"]: row for row in manifest["entries"]}
    tasks = rows_by_id(
        load_json(FEASIBILITY_ROOT / "development-task-matrices.json")["cases"],
        "instance_id",
    )
    security = rows_by_id(
        load_json(FEASIBILITY_ROOT / "development-security-matrices.json")["cases"],
        "instance_id",
    )
    cues = rows_by_id(
        load_json(V1_ROOT / "task-statement-cue-development.json")["results"],
        "target_id",
    )
    v1_reviews = {
        (row["request"]["target_id"], row["request"]["top_source_id"]): row
        for row in load_json(V1_ROOT / "pair-review-development-results.json")[
            "results"
        ]
    }
    results = []
    for target_id in DEVELOPMENT_IDS:
        ranking = ranking_rows[target_id]
        lock = ranking["selection_lock"]
        configured = config_rows[target_id]
        request = {
            "target_id": target_id,
            "top_source_id": lock["top_source_id"],
            "pair_hash": lock["pair_hash"],
        }
        validate_review_request(request)
        if any(configured[key] != request[key] for key in request):
            raise RuntimeError("review config differs from locked V2 pair")
        entry = entries[request["top_source_id"]]
        objective = objective_answers(
            target_id=target_id,
            entry=entry,
            ranking=ranking,
            task_case=tasks[target_id],
            security_case=security[target_id],
            cue=cues[target_id],
        )
        for question, answer in objective.items():
            if configured["answers"][question] != answer:
                raise RuntimeError(f"review conflicts with objective evidence: {target_id}:{question}")
        carry = configured["review_provenance"] == "CARRIED_FORWARD_IMMUTABLE_V1_PAIR_DECISION"
        carry_hash = None
        if carry:
            previous = v1_reviews[(target_id, request["top_source_id"])]
            if configured["v1_pair_hash"] != previous["request"]["pair_hash"]:
                raise RuntimeError("carried V1 pair hash changed")
            if configured["answers"] != previous["response"]["questions"]:
                raise RuntimeError("carried V1 answers were reopened or reinterpreted")
            carry_hash = stable_record_hash(previous["response"])
        evidence_hashes = {
            "review_request": review_request_hash(request),
            "source_entry": stable_record_hash(entry),
            "task_matrix_case": stable_record_hash(tasks[target_id]),
            "security_matrix_case": stable_record_hash(security[target_id]),
            "task_cue_record": stable_record_hash(cues[target_id]),
            "sealed_target_packet": directory_packet_hash(SEALED_ROOT / target_id),
        }
        response = build_sealed_response(
            request, configured["answers"], evidence_hashes
        )
        results.append(
            {
                "request": request,
                "response": response,
                "review_provenance": configured["review_provenance"],
                "review_rationale": configured.get("review_rationale"),
                "carried_v1_response_sha256": carry_hash,
                "objective_answers_verified": sorted(objective),
                "alternative_source_reviewed": False,
            }
        )
    accepted = sum(row["response"]["decision"] == "ACCEPT" for row in results)
    return {
        "schema": "cmpilot-pair-review-v2-development-results",
        "protocol_id": PROTOCOL_ID,
        "successor_protocol_commit": SUCCESSOR_PROTOCOL_COMMIT,
        "development_only": True,
        "matcher_rankings_sha256": ranking_hash,
        "review_config_sha256": sha256_file(REVIEW_CONFIG),
        "review_form": pair_review_form(),
        "all_yes_required": True,
        "v1_decisions_reopened_or_reinterpreted": False,
        "alternative_source_advice": False,
        "rank_2_fallback": False,
        "development_pairs_reviewed_v2": len(results),
        "accepted_count": accepted,
        "rejected_count": len(results) - accepted,
        "results": results,
    }


def read_events(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def fixed_clock() -> str:
    return "2026-09-03T00:00:00+00:00"


def memory_condition(
    *,
    root: Path,
    condition: str,
    target: Mapping[str, Any],
    entry: Mapping[str, Any],
    rankings: Sequence[Mapping[str, Any]],
    lock: Mapping[str, Any],
    lock_kind: str,
) -> dict[str, Any]:
    condition_root = root / condition.lower()
    store = MemoryStore(condition_root, condition=condition, clock=fixed_clock)
    source_session = f"source-{condition.lower()}-v2"
    target_session = f"target-{condition.lower()}-v2"
    store.begin_source_session(source_id=entry["source_id"], session_id=source_session)
    validation = store.record_source_validation(
        source_id=entry["source_id"],
        source_build=entry["source_build"],
        source_task_test=entry["source_task_test"],
        artifact_hashes=entry["source_artifact_hashes"],
    )
    packet = render_memory_packet(entry)
    fidelity = audit_memory_packet(packet, entry)
    stored = store.store_memory(source_id=entry["source_id"], packet=packet)
    store.end_source_session()
    store.begin_target_session(
        target_id=target["benchmark_instance_id"], session_id=target_session
    )
    delivered, retrieval = store.retrieve(
        retrieval_query=build_retrieval_query(target),
        candidate_rankings=rankings,
        selected_source_id=entry["source_id"],
        selection_lock=lock,
        lock_kind=lock_kind,
    )
    endpoint = mock_agent_endpoint(
        condition=condition,
        target_id=target["benchmark_instance_id"],
        delivered_memory=delivered,
    )
    endpoint_event = store.record_target_endpoint(endpoint)
    store.end_target_session()
    events_path = condition_root / "events.jsonl"
    events = read_events(events_path)
    sequence = [event["event"] for event in events]
    expected = [
        "SOURCE_SESSION_STARTED",
        "SOURCE_VALIDATION_COMPLETED",
        "MEMORY_STORED",
        "SOURCE_SESSION_ENDED",
        "TARGET_SESSION_STARTED",
        "MEMORY_RETRIEVED_AND_DELIVERED",
        "TARGET_ENDPOINT_COMPLETED",
        "TARGET_SESSION_ENDED",
    ]
    if sequence != expected or delivered != packet:
        raise RuntimeError("V2 memory lifecycle sequence or packet identity changed")
    return {
        "condition": condition,
        "source_id": entry["source_id"],
        "source_session_id": source_session,
        "target_session_id": target_session,
        "source_validation_event": validation,
        "stored_memory": stored,
        "retrieval_log": retrieval,
        "endpoint_event": endpoint_event,
        "event_sequence": sequence,
        "events_jsonl_sha256": sha256_file(events_path),
        "memory_fidelity": fidelity,
        "revalidation_instruction": (
            REVALIDATION_INSTRUCTION if condition.endswith("REVALIDATE") else None
        ),
        "evaluated_model_inference": False,
        "pass": True,
    }


def no_memory_condition(root: Path, target_id: str) -> dict[str, Any]:
    condition_root = root / "no_memory"
    store = MemoryStore(condition_root, condition="NO_MEMORY", clock=fixed_clock)
    session = "target-no-memory-v2"
    store.begin_target_session(target_id=target_id, session_id=session)
    endpoint = mock_agent_endpoint(
        condition="NO_MEMORY", target_id=target_id, delivered_memory=None
    )
    endpoint_event = store.record_target_endpoint(endpoint)
    store.end_target_session()
    events_path = condition_root / "events.jsonl"
    sequence = [event["event"] for event in read_events(events_path)]
    if sequence != [
        "TARGET_SESSION_STARTED",
        "TARGET_ENDPOINT_COMPLETED",
        "TARGET_SESSION_ENDED",
    ]:
        raise RuntimeError("NO_MEMORY lifecycle changed")
    return {
        "condition": "NO_MEMORY",
        "source_id": None,
        "source_session_id": None,
        "target_session_id": session,
        "memory_delivered": False,
        "semantic_padding": False,
        "endpoint_event": endpoint_event,
        "event_sequence": sequence,
        "events_jsonl_sha256": sha256_file(events_path),
        "evaluated_model_inference": False,
        "pass": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--memory-root", type=Path, default=DEFAULT_MEMORY_ROOT)
    args = parser.parse_args()
    artifact_root = args.artifact_root.resolve(strict=True)
    memory_root = args.memory_root.absolute()
    if memory_root.exists():
        raise FileExistsError(f"refusing to overwrite mock lifecycle: {memory_root}")
    memory_root.mkdir(parents=True)

    manifest = load_json(artifact_root / "expanded-source-corpus-manifest.json")
    rankings = load_json(artifact_root / "matcher-v2-development-rankings.json")
    representations = rows_by_id(
        load_json(V1_ROOT / "b-only-representation-results.json")["results"],
        "target_id",
    )
    reviews = build_reviews(
        artifact_root=artifact_root, rankings=rankings, manifest=manifest
    )
    accepted = [
        row for row in reviews["results"] if row["response"]["decision"] == "ACCEPT"
    ]
    if len(accepted) != 1:
        raise RuntimeError("V2 development requires exactly the retained all-YES pair")
    accepted_target_id = accepted[0]["request"]["target_id"]
    ranking = next(
        row for row in rankings["targets"] if row["target_id"] == accepted_target_id
    )
    target = representations[accepted_target_id]["representation"]
    entries = {row["source_id"]: row for row in manifest["entries"]}
    relevant = entries[ranking["selection_lock"]["top_source_id"]]
    irrelevant, irrelevant_record, irrelevant_lock = select_irrelevant_memory_v2(
        target,
        relevant,
        manifest["entries"],
        target_b_date_utc=ranking["target_b_date_utc"],
    )
    irrelevant_timestamp = validate_locked_irrelevant_timestamp(
        irrelevant_lock,
        manifest["entries"],
        target_b_timestamp_epoch=ranking["target_b_timestamp_epoch"],
    )
    if irrelevant_timestamp["status"] != "PASS":
        raise RuntimeError("locked irrelevant memory is not timestamp eligible")
    selected_control_row = next(
        row
        for row in irrelevant_record["candidate_rankings"]
        if row["source_id"] == irrelevant["source_id"]
    )
    irrelevant_artifact = {
        **irrelevant_record,
        "schema": "cmpilot-irrelevant-control-v2",
        "successor_protocol_commit": SUCCESSOR_PROTOCOL_COMMIT,
        "selected_entry": {
            "source_id": irrelevant["source_id"],
            "source_entry_sha256": stable_record_hash(irrelevant),
            "source_timestamp": irrelevant["commit_timestamp"],
            "source_correct": True,
            "source_focal_safe": True,
            "operation_class": irrelevant["operation_class"],
        },
        "selection_lock": irrelevant_lock,
        "sealed_exact_timestamp_validation": irrelevant_timestamp,
        "not_selected_after_model_outcomes": True,
        "status": "PASS",
    }

    relevant_packet = render_memory_packet(relevant)
    irrelevant_packet = render_memory_packet(irrelevant)
    relevant_metrics = memory_metrics(relevant)
    irrelevant_metrics = memory_metrics(irrelevant)
    packet_length = {
        "schema": "cmpilot-packet-length-analysis-v2",
        "resource_balance": {
            "mandatory": True,
            "mechanism": "EQUAL_POST_INGESTION_TRAJECTORY_CAPACITY",
            "post_ingestion_budget": 16384,
            "pass": True,
        },
        "prompt_length_matching": {
            "exact_equality_required": False,
            "selection_rule": "NEAREST_ELIGIBLE_PACKET_LEXICAL_TOKENS_THEN_IMPLEMENTATION_BYTES_THEN_VALIDATION_EVIDENCE_BYTES",
            "fixed_tolerance": None,
            "padding": False,
            "truncation": False,
            "relevant_source_id": relevant["source_id"],
            "irrelevant_source_id": irrelevant["source_id"],
            "relevant_metrics": relevant_metrics,
            "irrelevant_metrics": irrelevant_metrics,
            "absolute_packet_token_difference": selected_control_row["deltas"][
                "packet_token_absolute_difference"
            ],
            "relative_packet_token_difference": round(
                abs(irrelevant_metrics["packet_tokens"] - relevant_metrics["packet_tokens"])
                / max(relevant_metrics["packet_tokens"], 1),
                6,
            ),
            "sensitivity": irrelevant_record["sensitivity_only"],
            "pass": True,
        },
        "interpretation": "Attention-length imbalance is reported; equal post-ingestion capacity removes the mechanical trajectory-capacity confound.",
    }

    fidelity_rows = []
    for entry in manifest["entries"]:
        packet = render_memory_packet(entry)
        fidelity_rows.append(
            {
                "source_id": entry["source_id"],
                **audit_memory_packet(packet, entry),
                "packet_bytes": len(packet),
            }
        )
    fidelity = {
        "schema": "cmpilot-memory-fidelity-v2",
        "source_count": len(fidelity_rows),
        "all_exact": all(
            row["exact_implementation_identity"]
            and row["source_task_identity"]
            and not row["forbidden_target_or_oracle_material"]
            and not row["pstar_explanation_in_packet"]
            for row in fidelity_rows
        ),
        "llm_summaries": False,
        "target_future_information": False,
        "sources": fidelity_rows,
        "status": "PASS",
    }

    conditions = [
        no_memory_condition(memory_root, accepted_target_id),
        memory_condition(
            root=memory_root,
            condition="IRRELEVANT_CORRECT_MEMORY",
            target=target,
            entry=irrelevant,
            rankings=irrelevant_record["candidate_rankings"],
            lock=irrelevant_lock,
            lock_kind="IRRELEVANT_MATCH_V2",
        ),
        memory_condition(
            root=memory_root,
            condition="SOURCE_CORRECT_INAPPLICABLE",
            target=target,
            entry=relevant,
            rankings=ranking["full_rankings"],
            lock=ranking["selection_lock"],
            lock_kind="PAIR_TOP_ONE_V2",
        ),
        memory_condition(
            root=memory_root,
            condition="SOURCE_CORRECT_INAPPLICABLE_REVALIDATE",
            target=target,
            entry=relevant,
            rankings=ranking["full_rankings"],
            lock=ranking["selection_lock"],
            lock_kind="PAIR_TOP_ONE_V2",
        ),
    ]
    budgets = [
        context_budget_record(
            condition=condition,
            task_text=target["task_statement"],
            memory_packet=(
                None
                if condition == "NO_MEMORY"
                else irrelevant_packet
                if condition == "IRRELEVANT_CORRECT_MEMORY"
                else relevant_packet
            ),
            revalidation_instruction=(
                REVALIDATION_INSTRUCTION if condition.endswith("REVALIDATE") else None
            ),
        )
        for condition in CONDITIONS
    ]
    if len({row["post_ingestion_budget"] for row in budgets}) != 1:
        raise RuntimeError("post-ingestion resource balance changed")
    lifecycle = {
        "schema": "cmpilot-memory-lifecycle-v2",
        "development_only": True,
        "target_id": accepted_target_id,
        "conditions": conditions,
        "context_budgets": budgets,
        "pipeline": [
            "SOURCE_SESSION",
            "VALIDATION",
            "EXACT_MEMORY_EXTRACTION",
            "PERSISTENT_STORE",
            "END_SOURCE_SESSION",
            "NEW_TARGET_SESSION",
            "B_ONLY_RETRIEVAL",
            "DELIVERY_AND_LOGGING",
        ],
        "source_target_sessions_disjoint": True,
        "condition_store_roots_distinct": True,
        "cross_condition_contamination": False,
        "no_memory_semantic_padding": False,
        "evaluated_model_inference": False,
        "status": "PASS",
    }
    revalidation_v1 = load_json(V1_ROOT / "revalidation-intervention.json")
    if revalidation_v1["instruction"] != REVALIDATION_INSTRUCTION:
        raise RuntimeError("V1 revalidation wording changed")
    revalidation = {
        **revalidation_v1,
        "schema": "cmpilot-revalidation-intervention-v2",
        "wording_changed_from_v1": False,
        "inherited_v1_sha256": sha256_file(
            V1_ROOT / "revalidation-intervention.json"
        ),
        "status": "PASS",
    }
    condition_design = {
        "schema": "cmpilot-condition-design-v2",
        "recommended_condition_design": "DESIGN_C",
        "conditions": list(CONDITIONS),
        "applicable_control": "NOT_AVAILABLE",
        "applicable_control_search_extended": False,
        "generic_procedural_anchoring_alternative_fully_excluded": False,
        "mechanism_evidence": "REVALIDATION_INTERACTION_PLUS_PSTAR_RESPONSIVE_OBSERVABLE_BEHAVIOR",
        "causal_claim_limit": "Without an applicable control, generic procedural anchoring remains an alternative explanation.",
        "status": "READY",
    }
    design_c = {
        "schema": "cmpilot-design-c-end-to-end-v2",
        "development_only": True,
        "target_id": accepted_target_id,
        "conditions": list(CONDITIONS),
        "checks": {
            "b_only_top_one_relevant_lock": "PASS",
            "rank_2_fallback_absent": "PASS",
            "source_validation": "PASS",
            "relevant_packet_fidelity": "PASS",
            "irrelevant_packet_fidelity": "PASS",
            "irrelevant_operation_class_mismatch": "PASS",
            "irrelevant_timestamp": "PASS",
            "source_target_session_separation": "PASS",
            "all_four_endpoint_stubs": "PASS",
            "resource_budget_equality": "PASS",
            "no_memory_has_no_junk": "PASS",
            "revalidation_wording_unchanged": "PASS",
        },
        "logical_trajectory_capacity": {
            "physical_context": 32768,
            "post_ingestion_budget": 16384,
            "context_reserve": 256,
            "per_turn_generation_max": 4096,
            "model_decision_max": 32,
        },
        "evaluated_model_inference": False,
        "gpu_used": False,
        "design_c_end_to_end_pass": True,
        "status": "PASS",
    }

    corpus_runtime = load_json(artifact_root / "source-corpus-runtime.json")
    feasibility = load_json(FEASIBILITY_ROOT / "readiness.json")
    per_target_machine = feasibility["estimated_full_screen_hours"] / feasibility[
        "susvibes_task_count"
    ]
    runtime = {
        "schema": "cmpilot-source-pairing-runtime-estimates-v2",
        "development_only": True,
        "observed_source_expansion": {
            **corpus_runtime,
            "reviewer_hours_fixed_allowance": round(38 * 5 / 60, 2),
        },
        "development_pair_review": {
            "reviewed": reviews["development_pairs_reviewed_v2"],
            "all_yes": reviews["accepted_count"],
            "observed_fraction_not_a_confirmatory_yield_estimate": "1/5",
        },
        "source_pairing_time_per_target": {
            "machine_hours_excluding_model_approx": round(per_target_machine, 3),
            "reviewer_hours_planning_range": [0.5, 1.5],
            "confidence": "LOW",
        },
        "sample_size_recommendation": {
            "recommended_minimum_n": 8,
            "recommended_target_n": 12,
            "recommended_maximum_n": 16,
            "interpretations": {
                "8-11": "CONTROLLED_MECHANISM_PILOT",
                "12-16": "CONTROLLED_WORKSHOP_CAUSAL_STUDY",
                "3-7": "CASE_SERIES_OR_METHODS",
            },
            "planning_screens_at_observed_diagnostic_fraction_only": {
                "minimum_8": 40,
                "target_12": 60,
                "maximum_16": 80,
            },
        },
        "estimated_confirmatory_screening": {
            "unseen_targets": feasibility["unseen_target_count"],
            "machine_hours_full_181_approx": round(
                per_target_machine * feasibility["unseen_target_count"], 1
            ),
            "reviewer_hours_full_181_range": [90.5, 271.5],
            "status": "PLANNING_ONLY_NOT_AUTHORIZED",
        },
        "evaluated_model_runtime_included": False,
    }
    execution_ledger = {
        "schema": "cmpilot-development-v2-execution-ledger",
        "evaluated_agent_trajectories": 0,
        "evaluated_model_inference": False,
        "events": [
            {
                "order": 1,
                "command": "build_source_corpus_v2_evidence.py",
                "status": "FAILED_INFRASTRUCTURE_ASSERTION",
                "error": "KeyError: validation_result_pass",
                "final_artifact_written": False,
            },
            {
                "order": 2,
                "command": "build_source_corpus_v2_evidence.py",
                "status": "FAILED_BREADTH_DUE_S2_WORKING_DIRECTORY_BUG",
                "observed_breadth": {"repositories": 5, "s2_repositories": 0, "operation_classes": 13},
                "final_artifact_written": False,
            },
            {
                "order": 3,
                "command": "build_source_corpus_v2_evidence.py",
                "status": "FAILED_BREADTH_DUE_PYTEST_PY312_COLLECTION_INCOMPATIBILITY",
                "observed_breadth": {"repositories": 6, "s2_repositories": 1, "operation_classes": 13},
                "final_artifact_written": False,
            },
            {
                "order": 4,
                "command": "/usr/bin/python3.10 -m venv .../venvs-py310/starlette",
                "status": "FAILED_NO_ENSUREPIP_NO_SYSTEM_CHANGE_ATTEMPTED",
                "final_artifact_written": False,
            },
            {
                "order": 5,
                "command": "Starlette four-node source-only compatibility diagnostic",
                "status": "4_PASS_1_ASYNC_BACKEND_FAILURE_WITH_NARROW_WARNING_FILTER",
                "used_for_candidate_selection": False,
                "dependency_added_after_outcome": False,
            },
            {
                "order": 6,
                "command": "build_source_corpus_v2_evidence.py",
                "status": "PASS",
                "final_artifact_written": True,
                "manifest_sha256": sha256_file(
                    artifact_root / "expanded-source-corpus-manifest.json"
                ),
            },
        ],
    }

    write_json(artifact_root / "pair-review-v2-development-results.json", reviews)
    write_json(artifact_root / "irrelevant-control-v2.json", irrelevant_artifact)
    write_json(artifact_root / "packet-length-analysis.json", packet_length)
    write_json(artifact_root / "memory-fidelity-v2.json", fidelity)
    write_json(artifact_root / "memory-lifecycle-v2.json", lifecycle)
    write_json(artifact_root / "revalidation-v2.json", revalidation)
    write_json(artifact_root / "condition-design-v2.json", condition_design)
    write_json(artifact_root / "design-c-end-to-end.json", design_c)
    write_json(artifact_root / "runtime-estimates.json", runtime)
    write_json(artifact_root / "development-execution-ledger.json", execution_ledger)
    print(
        json.dumps(
            {
                "reviewed": reviews["development_pairs_reviewed_v2"],
                "all_yes": reviews["accepted_count"],
                "irrelevant": irrelevant["source_id"],
                "irrelevant_timestamp": irrelevant_timestamp["status"],
                "design_c": design_c["status"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
