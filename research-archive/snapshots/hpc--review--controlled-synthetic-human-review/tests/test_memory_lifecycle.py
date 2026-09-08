from __future__ import annotations

import json
from pathlib import Path

import pytest

from cmpilot.memory_lifecycle import (
    CONDITIONS,
    CONTEXT_RESERVE,
    MODEL_DECISION_MAX,
    PER_TURN_GENERATION_MAX,
    PHYSICAL_CONTEXT,
    POST_INGESTION_BUDGET,
    REVALIDATION_INSTRUCTION,
    MemoryLifecycleError,
    MemoryStore,
    audit_memory_packet,
    automated_behavior_features,
    build_retrieval_query,
    context_budget_record,
    enforce_irrelevant_lock,
    irrelevant_lock,
    mock_agent_endpoint,
    packet_section,
    rank_irrelevant_memories,
    render_memory_packet,
    select_irrelevant_memory,
    sha256_bytes,
)
from cmpilot.source_pairing import stable_record_hash
from cmpilot.susvibes_feasibility import DEVELOPMENT_IDS


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "artifacts/context-dependent-memory-source-pairing"


def load(name: str) -> dict:
    return json.loads((ARTIFACT_ROOT / name).read_text(encoding="utf-8"))


def wagtail_fixture() -> tuple[dict, dict, dict, list[dict]]:
    manifest = load("source-corpus-manifest.json")
    rankings = load("matcher-development-rankings.json")
    representations = load("b-only-representation-results.json")
    target_id = DEVELOPMENT_IDS[2]
    target = next(
        row["representation"]
        for row in representations["results"]
        if row["target_id"] == target_id
    )
    ranking = next(row for row in rankings["targets"] if row["target_id"] == target_id)
    lock = ranking["development_selection"]["lock"]
    relevant = next(
        entry for entry in manifest["entries"] if entry["source_id"] == lock["top_source_id"]
    )
    return target, relevant, lock, manifest["entries"]


def test_memory_packet_preserves_exact_source_bytes_and_excludes_pstar() -> None:
    _, entry, _, _ = wagtail_fixture()
    packet = render_memory_packet(entry)
    audit = audit_memory_packet(packet, entry)
    assert packet_section(packet, "SOURCE_IMPLEMENTATION") == entry[
        "source_implementation_or_patch"
    ].encode()
    assert packet_section(packet, "SOURCE_TASK") == entry["source_task_description"].encode()
    assert audit["exact_implementation_identity"] is True
    assert audit["source_task_identity"] is True
    assert entry["focal_source_safety"]["pstar"]["proposition"].encode() not in packet
    assert b"<PSTAR>" not in packet
    assert packet.count(b"<SOURCE_") == 3


def test_memory_store_persists_and_separates_source_target_and_condition_sessions(
    tmp_path: Path,
) -> None:
    target, entry, lock, _ = wagtail_fixture()
    packet = render_memory_packet(entry)
    root = tmp_path / "relevant"
    clock = lambda: "2026-09-02T00:00:00+00:00"
    store = MemoryStore(root, condition="SOURCE_CORRECT_INAPPLICABLE", clock=clock)
    store.begin_source_session(source_id=entry["source_id"], session_id="source-session-1")
    with pytest.raises(MemoryLifecycleError, match="active"):
        store.begin_target_session(target_id=target["benchmark_instance_id"], session_id="target-1")
    store.record_source_validation(
        source_id=entry["source_id"],
        source_build=entry["source_build"],
        source_task_test=entry["source_task_test"],
        artifact_hashes=entry["source_artifact_hashes"],
    )
    metadata = store.store_memory(source_id=entry["source_id"], packet=packet)
    store.end_source_session()

    reopened = MemoryStore(root, condition="SOURCE_CORRECT_INAPPLICABLE", clock=clock)
    assert metadata["memory_id"] in reopened.entries
    with pytest.raises(MemoryLifecycleError, match="cross-condition"):
        MemoryStore(root, condition="IRRELEVANT_CORRECT_MEMORY", clock=clock)
    reopened.begin_target_session(
        target_id=target["benchmark_instance_id"], session_id="target-session-1"
    )
    delivered, log = reopened.retrieve(
        retrieval_query=build_retrieval_query(target),
        candidate_rankings=[
            {
                "source_id": entry["source_id"],
                "rank": 1,
                "scores": {"semantic_similarity": 0.1},
            }
        ],
        selected_source_id=entry["source_id"],
        selection_lock=lock,
        lock_kind="PAIR_TOP_ONE",
    )
    endpoint = mock_agent_endpoint(
        condition="SOURCE_CORRECT_INAPPLICABLE",
        target_id=target["benchmark_instance_id"],
        delivered_memory=delivered,
    )
    reopened.record_target_endpoint(endpoint)
    reopened.end_target_session()
    assert delivered == packet
    assert log["source_id"] == entry["source_id"]
    assert log["memory_hash"] == sha256_bytes(packet)
    assert log["source_session_id"] == "source-session-1"
    assert log["retrieval_query"]
    assert log["candidate_ids"] == [entry["source_id"]]
    assert log["candidate_ranks"] == {entry["source_id"]: 1}
    assert log["selected_memory_id"] == metadata["memory_id"]
    assert log["delivered_bytes_hash"] == sha256_bytes(packet)
    assert log["target_session_id"] == "target-session-1"
    events = [json.loads(line) for line in (root / "events.jsonl").read_text().splitlines()]
    assert [event["event"] for event in events] == [
        "SOURCE_SESSION_STARTED",
        "SOURCE_VALIDATION_COMPLETED",
        "MEMORY_STORED",
        "SOURCE_SESSION_ENDED",
        "TARGET_SESSION_STARTED",
        "MEMORY_RETRIEVED_AND_DELIVERED",
        "TARGET_ENDPOINT_COMPLETED",
        "TARGET_SESSION_ENDED",
    ]


def test_source_validation_must_pass_inside_matching_source_session(
    tmp_path: Path,
) -> None:
    _, entry, _, _ = wagtail_fixture()
    store = MemoryStore(tmp_path, condition="SOURCE_CORRECT_INAPPLICABLE")
    with pytest.raises(MemoryLifecycleError, match="outside"):
        store.record_source_validation(
            source_id=entry["source_id"],
            source_build=entry["source_build"],
            source_task_test=entry["source_task_test"],
            artifact_hashes=entry["source_artifact_hashes"],
        )
    store.begin_source_session(source_id=entry["source_id"], session_id="source-1")
    failed = {**entry["source_task_test"], "classification": "FAIL"}
    with pytest.raises(MemoryLifecycleError, match="SOURCE_TASK_TEST"):
        store.record_source_validation(
            source_id=entry["source_id"],
            source_build=entry["source_build"],
            source_task_test=failed,
            artifact_hashes=entry["source_artifact_hashes"],
        )
    event = store.record_source_validation(
        source_id=entry["source_id"],
        source_build=entry["source_build"],
        source_task_test=entry["source_task_test"],
        artifact_hashes=entry["source_artifact_hashes"],
    )
    assert event["source_build_result"] == "PASS"
    assert event["source_task_test_result"] == "PASS"


def test_strict_irrelevant_selector_rejects_postdated_or_poorly_matched_sources() -> None:
    target, relevant, _, entries = wagtail_fixture()
    record = rank_irrelevant_memories(target, relevant, entries)
    assert record["status"] == "NOT_AVAILABLE"
    assert record["selected"] is None
    assert record["selected_source_id"] is None
    assert record["accepted_count"] == 0
    assert record["selection_uses_target_oracle"] is False
    assert all(not row["hard_gate_pass"] for row in record["candidate_rankings"])
    postdated = next(
        row
        for row in record["candidate_rankings"]
        if row["source_id"] == "src-django-signed-session-decode"
    )
    assert postdated["available_before_target_B"] is False
    with pytest.raises(MemoryLifecycleError, match="NO_MATCHED"):
        select_irrelevant_memory(target, relevant, entries)


def test_irrelevant_lock_is_immutable_and_has_no_fallback() -> None:
    target, relevant, _, _ = wagtail_fixture()
    excluded_unit_record = {
        "scope": "SYNTHETIC_LOCK_MECHANISM_ONLY_NOT_A_SOURCE_SELECTION",
        "selected_source_id": relevant["source_id"],
    }
    lock = irrelevant_lock(
        target_id=target["benchmark_instance_id"],
        selected_source_id=relevant["source_id"],
        selector_record=excluded_unit_record,
    )
    enforce_irrelevant_lock(lock, relevant["source_id"])
    with pytest.raises(PermissionError, match="fallback"):
        enforce_irrelevant_lock(lock, "rank-2-is-forbidden")


def test_context_budget_is_equal_and_no_memory_has_no_padding() -> None:
    target, relevant, _, entries = wagtail_fixture()
    relevant_packet = render_memory_packet(relevant)
    excluded_unit_packet = render_memory_packet(
        next(entry for entry in entries if entry["source_id"] != relevant["source_id"])
    )
    records = [
        context_budget_record(
            condition="NO_MEMORY",
            task_text=target["task_statement"],
            memory_packet=None,
            revalidation_instruction=None,
        ),
        context_budget_record(
            condition="IRRELEVANT_CORRECT_MEMORY",
            task_text=target["task_statement"],
            memory_packet=excluded_unit_packet,
            revalidation_instruction=None,
        ),
        context_budget_record(
            condition="SOURCE_CORRECT_INAPPLICABLE",
            task_text=target["task_statement"],
            memory_packet=relevant_packet,
            revalidation_instruction=None,
        ),
        context_budget_record(
            condition="SOURCE_CORRECT_INAPPLICABLE_REVALIDATE",
            task_text=target["task_statement"],
            memory_packet=relevant_packet,
            revalidation_instruction=REVALIDATION_INSTRUCTION,
        ),
    ]
    assert tuple(record["condition"] for record in records) == CONDITIONS
    assert {record["physical_context"] for record in records} == {PHYSICAL_CONTEXT}
    assert {record["post_ingestion_budget"] for record in records} == {
        POST_INGESTION_BUDGET
    }
    assert {record["context_reserve"] for record in records} == {CONTEXT_RESERVE}
    assert {record["per_turn_generation_max"] for record in records} == {
        PER_TURN_GENERATION_MAX
    }
    assert {record["model_decision_max"] for record in records} == {
        MODEL_DECISION_MAX
    }
    assert records[0]["no_memory_semantic_padding"] is False
    assert all(
        record["trajectory_capacity_reduced_by_revalidation"] is False
        for record in records
    )
    with pytest.raises(MemoryLifecycleError, match="wording changed"):
        context_budget_record(
            condition="SOURCE_CORRECT_INAPPLICABLE_REVALIDATE",
            task_text="task",
            memory_packet=relevant_packet,
            revalidation_instruction=REVALIDATION_INSTRUCTION + " Extra.",
        )
    with pytest.raises(MemoryLifecycleError, match="actual memory"):
        context_budget_record(
            condition="IRRELEVANT_CORRECT_MEMORY",
            task_text="task",
            memory_packet=None,
            revalidation_instruction=None,
        )


def test_behavior_features_report_observables_without_hidden_reasoning() -> None:
    features = automated_behavior_features(
        source_implementation="def check(url):\n    return parse(url)\n",
        target_patch="def check(path):\n    return parse(path)\n",
        action_log=[
            {"kind": "READ", "path": "settings.py", "timestamp": "t1"},
            {"kind": "COMMAND", "command": "pytest tests", "timestamp": "t2"},
        ],
        pstar_observable_terms=["path", "scheme"],
    )
    assert features["hidden_reasoning_inferred"] is False
    assert features["api_sequence_reuse_count"] == 1
    assert features["functional_test_commands"] == ["pytest tests"]
    assert features["configuration_context_reads"] == ["settings.py"]
    assert features["action_order"] == ["READ", "COMMAND"]


def test_mock_endpoint_never_runs_an_evaluated_model() -> None:
    result = mock_agent_endpoint(
        condition="NO_MEMORY", target_id=DEVELOPMENT_IDS[2], delivered_memory=None
    )
    assert result["endpoint"] == "DETERMINISTIC_STUB_NO_MODEL"
    assert result["evaluated_model_inference"] is False
    assert result["patch"] == ""
    assert stable_record_hash(result)


def test_no_memory_has_logged_target_session_and_cannot_retrieve(tmp_path: Path) -> None:
    target, _, lock, _ = wagtail_fixture()
    store = MemoryStore(tmp_path, condition="NO_MEMORY")
    with pytest.raises(MemoryLifecycleError, match="source session"):
        store.begin_source_session(source_id="source", session_id="source-1")
    store.begin_target_session(
        target_id=target["benchmark_instance_id"], session_id="target-no-memory-1"
    )
    with pytest.raises(MemoryLifecycleError, match="cannot retrieve"):
        store.retrieve(
            retrieval_query="query",
            candidate_rankings=[],
            selected_source_id="source",
            selection_lock=lock,
            lock_kind="PAIR_TOP_ONE",
        )
    endpoint = mock_agent_endpoint(
        condition="NO_MEMORY",
        target_id=target["benchmark_instance_id"],
        delivered_memory=None,
    )
    store.record_target_endpoint(endpoint)
    store.end_target_session()
    events = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert [event["event"] for event in events] == [
        "TARGET_SESSION_STARTED",
        "TARGET_ENDPOINT_COMPLETED",
        "TARGET_SESSION_ENDED",
    ]
