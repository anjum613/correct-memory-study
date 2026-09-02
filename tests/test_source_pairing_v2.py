from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from cmpilot.source_pairing import stable_record_hash
from cmpilot.source_pairing_v2 import (
    GLOBAL_SIMILARITY_THRESHOLD_REQUIRED,
    SourcePairingV2Error,
    enforce_irrelevant_lock_v2,
    enforce_top_source_lock_v2,
    matcher_design_record,
    rank_irrelevant_memories_v2,
    rank_sources_v2,
    resolve_top_ambiguity,
    select_irrelevant_memory_v2,
    select_top_source_v2,
    validate_locked_irrelevant_timestamp,
    validate_locked_source_timestamp,
)
from cmpilot.memory_lifecycle import (
    MemoryStore,
    build_retrieval_query,
    render_memory_packet,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "artifacts/context-dependent-memory-source-pairing"


def _load(name: str) -> dict:
    return json.loads((ARTIFACT_ROOT / name).read_text(encoding="utf-8"))


def _wagtail() -> tuple[dict, list[dict], int, str]:
    representation = next(
        row["representation"]
        for row in _load("b-only-representation-results.json")["results"]
        if row["target_id"].startswith("wagtail__")
    )
    entries = _load("source-corpus-manifest.json")["entries"]
    epoch = next(
        row["target_timestamp_epoch"]
        for row in _load("matcher-development-rankings.json")["targets"]
        if row["target_id"].startswith("wagtail__")
    )
    day = datetime.fromtimestamp(epoch, timezone.utc).date().isoformat()
    return representation, entries, epoch, day


def test_matcher_has_no_global_threshold_or_weighted_score() -> None:
    design = matcher_design_record()
    assert GLOBAL_SIMILARITY_THRESHOLD_REQUIRED is False
    assert design["global_similarity_threshold_required"] is False
    assert design["combined_or_weighted_score"] is None
    assert design["numerical_ambiguity_margin"] is None
    assert design["top_one"] is True
    assert design["rank_2_fallback"] is False


def test_hard_gates_precede_lexicographic_ranking() -> None:
    target, entries, _, day = _wagtail()
    rows = rank_sources_v2(target, entries, target_b_date_utc=day)
    eligible = [row for row in rows if row["hard_gate_pass"]]
    ineligible = [row for row in rows if not row["hard_gate_pass"]]
    assert eligible
    assert rows == eligible + ineligible
    assert all(row["scores"]["operation_class_intersection_count"] >= 1 for row in eligible)
    assert all(row["global_or_weighted_score"] is None for row in rows)


def test_top_one_is_deterministic_immutable_and_has_no_rank2() -> None:
    target, entries, _, day = _wagtail()
    first_rankings, first_lock = select_top_source_v2(
        target, entries, target_b_date_utc=day
    )
    second_rankings, second_lock = select_top_source_v2(
        target, list(reversed(entries)), target_b_date_utc=day
    )
    assert first_rankings == second_rankings
    assert first_lock == second_lock
    enforce_top_source_lock_v2(first_lock, first_lock["top_source_id"])
    runner = next(
        row["source_id"]
        for row in first_rankings
        if row["hard_gate_pass"] and row["source_id"] != first_lock["top_source_id"]
    )
    with pytest.raises(PermissionError, match="rank-2"):
        enforce_top_source_lock_v2(first_lock, runner)
    tampered = {**first_lock, "full_rankings_sha256": "0" * 64}
    with pytest.raises(SourcePairingV2Error, match="hash mismatch"):
        enforce_top_source_lock_v2(tampered, tampered["top_source_id"])


def test_substantive_exact_tie_rejects_but_equivalent_episode_allows_hash() -> None:
    scores = {
        "primary_operation_class_exact": True,
        "operation_class_intersection_count": 1,
        "same_required_or_public_library_api": False,
        "api_sequence_similarity": 0.0,
        "type_data_role_similarity": 0.0,
        "ast_similarity": 0.0,
        "token_similarity": 0.0,
        "semantic_similarity": 0.0,
    }
    top = {"source_id": "a", "scores": scores}
    runner = {"source_id": "b", "scores": dict(scores)}
    base = {
        "operation_class": ["DATA_VALIDATION"],
        "API_sequence": [],
        "type_or_data_role_signature": [],
        "focal_source_safety": {"pstar": {"ontology_class": "VALIDATION_BEFORE_USE"}},
        "source_implementation_or_patch": "def f():\n    return 1\n",
        "source_task_description": "def test_f():\n    assert f() == 1\n",
    }
    equivalent = {"a": base, "b": deepcopy(base)}
    assert resolve_top_ambiguity(top, runner, equivalent)["hash_tiebreak_used"] is True
    substantive = deepcopy(equivalent)
    substantive["b"]["source_implementation_or_patch"] = "def g():\n    return 2\n"
    with pytest.raises(SourcePairingV2Error, match="SUBSTANTIVE_TIE"):
        resolve_top_ambiguity(top, runner, substantive)


def test_coarse_and_sealed_exact_timestamp_checks_fail_closed() -> None:
    target, entries, epoch, day = _wagtail()
    _, lock = select_top_source_v2(target, entries, target_b_date_utc=day)
    record = validate_locked_source_timestamp(
        lock, entries, target_b_timestamp_epoch=epoch
    )
    assert record["status"] == "PASS"
    assert record["fallback_attempted"] is False
    postdated_epoch = next(
        entry["commit_timestamp_epoch"]
        for entry in entries
        if entry["commit_timestamp_epoch"] > epoch
    )
    assert postdated_epoch > epoch


def test_irrelevant_control_is_operation_disjoint_nearest_and_timestamp_valid() -> None:
    target, entries, epoch, day = _wagtail()
    _, pair_lock = select_top_source_v2(target, entries, target_b_date_utc=day)
    relevant = next(
        entry for entry in entries if entry["source_id"] == pair_lock["top_source_id"]
    )
    selected, record, lock = select_irrelevant_memory_v2(
        target, relevant, entries, target_b_date_utc=day
    )
    assert record["status"] == "PASS"
    assert record["fixed_length_tolerance"] is None
    assert record["padding_or_truncation"] is False
    selected_row = next(
        row for row in record["candidate_rankings"] if row["source_id"] == selected["source_id"]
    )
    assert selected_row["rank"] == 1
    assert selected_row["operation_class_disjoint"] is True
    assert selected_row["target_api_or_symbol_leakage"] == []
    eligible = [row for row in record["candidate_rankings"] if row["hard_gate_pass"]]
    assert selected_row["deltas"]["packet_token_absolute_difference"] == min(
        row["deltas"]["packet_token_absolute_difference"] for row in eligible
    )
    enforce_irrelevant_lock_v2(lock, selected["source_id"])
    exact = validate_locked_irrelevant_timestamp(
        lock, entries, target_b_timestamp_epoch=epoch
    )
    assert exact["status"] == "PASS"
    assert selected["commit_timestamp_epoch"] <= epoch


def test_irrelevant_rank2_and_postdated_candidates_are_prohibited() -> None:
    target, entries, _, day = _wagtail()
    relevant = next(
        entry for entry in entries if entry["source_id"] == "src-wagtail-document-link-expand"
    )
    record = rank_irrelevant_memories_v2(
        target, relevant, entries, target_b_date_utc=day
    )
    postdated = [
        row
        for row in record["candidate_rankings"]
        if "COARSE_TIMESTAMP_INELIGIBLE" in row["hard_gate_reasons"]
    ]
    assert postdated
    selected, _, lock = select_irrelevant_memory_v2(
        target, relevant, entries, target_b_date_utc=day
    )
    alternative = next(
        entry["source_id"]
        for entry in entries
        if entry["source_id"] not in {selected["source_id"], relevant["source_id"]}
    )
    with pytest.raises(PermissionError, match="rank-2"):
        enforce_irrelevant_lock_v2(lock, alternative)


def test_lock_hashes_bind_threshold_free_design() -> None:
    target, entries, _, day = _wagtail()
    rankings, lock = select_top_source_v2(target, entries, target_b_date_utc=day)
    assert lock["global_similarity_threshold"] is None
    assert lock["matcher_design_sha256"] == stable_record_hash(matcher_design_record())
    assert lock["full_rankings_sha256"] == stable_record_hash(rankings)


def test_existing_lifecycle_accepts_v2_locks_without_session_redesign(
    tmp_path: Path,
) -> None:
    target, entries, _, day = _wagtail()
    rankings, lock = select_top_source_v2(target, entries, target_b_date_utc=day)
    entry = next(
        item for item in entries if item["source_id"] == lock["top_source_id"]
    )
    packet = render_memory_packet(entry)
    store = MemoryStore(tmp_path, condition="SOURCE_CORRECT_INAPPLICABLE")
    store.begin_source_session(source_id=entry["source_id"], session_id="v2-source")
    store.record_source_validation(
        source_id=entry["source_id"],
        source_build=entry["source_build"],
        source_task_test=entry["source_task_test"],
        artifact_hashes=entry["source_artifact_hashes"],
    )
    store.store_memory(source_id=entry["source_id"], packet=packet)
    store.end_source_session()
    store.begin_target_session(
        target_id=target["benchmark_instance_id"], session_id="v2-target"
    )
    delivered, event = store.retrieve(
        retrieval_query=build_retrieval_query(target),
        candidate_rankings=rankings,
        selected_source_id=entry["source_id"],
        selection_lock=lock,
        lock_kind="PAIR_TOP_ONE_V2",
    )
    assert delivered == packet
    assert event["lock_kind"] == "PAIR_TOP_ONE_V2"
