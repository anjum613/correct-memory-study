"""Generic model-free V3 screening and DESIGN_C development plumbing."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence

from cmpilot.memory_lifecycle import (
    CONDITIONS,
    REVALIDATION_INSTRUCTION,
    MemoryStore,
    build_retrieval_query,
    context_budget_record,
    mock_agent_endpoint,
    render_memory_packet,
)
from cmpilot.pair_review_v3 import SealedEvidenceHandle, evaluate_sealed_pair_v3
from cmpilot.source_pairing import AuditedWorkspaceReader, stable_record_hash
from cmpilot.source_pairing_confirmatory_v2 import prepare_frozen_corpus_for_target
from cmpilot.source_pairing_v3 import (
    select_irrelevant_memory_v3,
    select_top_source_v3,
    validate_locked_irrelevant_timestamp_v3,
    validate_locked_source_timestamp_v3,
)
from cmpilot.source_validation import validate_source_correct_entry
from cmpilot.target_identity_v3 import (
    TargetIdentityScope,
    build_b_only_representation_v3,
)


FROZEN_SOURCE_CORPUS_COUNT = 50
ATTRITION_STAGES = (
    "TARGET_IDENTITY",
    "B_ONLY_REPRESENTATION",
    "SOURCE_TIER_PREPARATION",
    "SOURCE_CORRECT_CORPUS",
    "DETERMINISTIC_MATCHER",
    "TOP_SOURCE_LOCK",
    "EXACT_RELEVANT_TIMESTAMP",
    "PAIR_FOCAL_SOURCE_SAFETY",
    "TARGET_ELIGIBILITY",
    "SEALED_PAIR_REVIEW",
    "IRRELEVANT_MEMORY_SELECTION",
    "EXACT_IRRELEVANT_TIMESTAMP",
    "SCREENING_RESULT",
)


class ConfirmatoryV3Error(ValueError):
    """A generic V3 screening or mock-condition invariant failed."""


@dataclass
class AttritionLedgerV3:
    target_id: str
    records: list[dict[str, Any]] = field(default_factory=list)

    def record(
        self,
        stage: str,
        status: str,
        *,
        evidence: Mapping[str, Any] | None = None,
        reason: str | None = None,
    ) -> None:
        if stage not in ATTRITION_STAGES:
            raise ConfirmatoryV3Error("unknown V3 attrition stage")
        if self.records and ATTRITION_STAGES.index(stage) <= ATTRITION_STAGES.index(
            self.records[-1]["stage"]
        ):
            raise ConfirmatoryV3Error("V3 attrition stages are not monotonic")
        self.records.append(
            {
                "sequence": len(self.records) + 1,
                "target_id": self.target_id,
                "stage": stage,
                "status": status,
                "reason": reason,
                "evidence_sha256": None
                if evidence is None
                else stable_record_hash(evidence),
            }
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "cmpilot-complete-attrition-ledger-v3",
            "target_id": self.target_id,
            "records": list(self.records),
            "record_count": len(self.records),
            "model_outcomes_used": False,
        }


def _screening_halt(
    *,
    target_id: str,
    status: str,
    ledger: AttritionLedgerV3,
    representation: Mapping[str, Any],
    rankings: Sequence[Mapping[str, Any]],
    pair_lock: Mapping[str, Any],
    pair_review: Mapping[str, Any] | None,
) -> dict[str, Any]:
    ledger.record("SCREENING_RESULT", status, evidence=pair_review)
    return {
        "schema": "cmpilot-confirmatory-screening-result-v3",
        "target_id": target_id,
        "status": status,
        "target_representation": representation,
        "rankings": list(rankings),
        "pair_lock": pair_lock,
        "pair_review": pair_review,
        "attrition_ledger": ledger.as_dict(),
        "rank_2_fallback_attempted": False,
        "evaluated_model_inference": False,
    }


def screen_target_v3(
    *,
    target_id: str,
    scope: TargetIdentityScope,
    workspace_reader: AuditedWorkspaceReader,
    frozen_source_entries: Sequence[Mapping[str, Any]],
    target_b_date_utc: str,
    target_b_timestamp_epoch: int,
    sealed_evidence_handle: SealedEvidenceHandle,
) -> dict[str, Any]:
    """Run the production V3 screening path for one explicitly scoped target."""

    ledger = AttritionLedgerV3(target_id)
    scope.validate(target_id)
    ledger.record(
        "TARGET_IDENTITY",
        "PASS",
        evidence={
            "target_id": target_id,
            "scope_purpose": scope.purpose,
            "identity_list_sha256": scope.identity_list_sha256,
        },
    )
    representation = build_b_only_representation_v3(workspace_reader, scope=scope)
    if representation["benchmark_instance_id"] != target_id:
        raise ConfirmatoryV3Error("B-only representation target mismatch")
    ledger.record("B_ONLY_REPRESENTATION", "PASS", evidence=representation)
    if len(frozen_source_entries) != FROZEN_SOURCE_CORPUS_COUNT:
        raise ConfirmatoryV3Error("V3 source corpus is not the frozen 50-entry corpus")
    prepared_entries = prepare_frozen_corpus_for_target(
        frozen_source_entries, target_instance_id=target_id
    )
    ledger.record(
        "SOURCE_TIER_PREPARATION",
        "PASS",
        evidence={
            "target_id": target_id,
            "prepared_count": len(prepared_entries),
            "prepared_sha256": stable_record_hash(prepared_entries),
        },
    )
    for entry in prepared_entries:
        validate_source_correct_entry(entry, target_id=target_id)
    ledger.record(
        "SOURCE_CORRECT_CORPUS",
        "PASS",
        evidence={
            "source_correct": len(prepared_entries),
            "historical_focal_safety_used": False,
        },
    )
    rankings, pair_lock = select_top_source_v3(
        representation,
        prepared_entries,
        target_b_date_utc=target_b_date_utc,
        scope=scope,
    )
    ledger.record("DETERMINISTIC_MATCHER", "PASS", evidence={"rankings": rankings})
    ledger.record("TOP_SOURCE_LOCK", "PASS", evidence=pair_lock)
    exact_source_timestamp = validate_locked_source_timestamp_v3(
        pair_lock,
        prepared_entries,
        target_b_timestamp_epoch=target_b_timestamp_epoch,
    )
    ledger.record(
        "EXACT_RELEVANT_TIMESTAMP",
        exact_source_timestamp["status"],
        evidence=exact_source_timestamp,
    )
    if exact_source_timestamp["status"] != "PASS":
        return _screening_halt(
            target_id=target_id,
            status="REJECT",
            ledger=ledger,
            representation=representation,
            rankings=rankings,
            pair_lock=pair_lock,
            pair_review=None,
        )
    relevant = next(
        entry
        for entry in prepared_entries
        if entry["source_id"] == pair_lock["top_source_id"]
    )
    review = evaluate_sealed_pair_v3(
        target_id=target_id,
        top_source_id=str(pair_lock["top_source_id"]),
        pair_hash=str(pair_lock["pair_hash"]),
        sealed_evidence_handle=sealed_evidence_handle,
        pair_lock=pair_lock,
        source_entry=relevant,
        scope=scope,
    )
    pair_safety = review["pair_focal_safety"]
    target_eligibility = review["target_eligibility"]
    ledger.record(
        "PAIR_FOCAL_SOURCE_SAFETY", pair_safety["status"], evidence=pair_safety
    )
    ledger.record(
        "TARGET_ELIGIBILITY", target_eligibility["status"], evidence=target_eligibility
    )
    ledger.record("SEALED_PAIR_REVIEW", review["decision"], evidence=review)
    if target_eligibility["status"] == "INFRASTRUCTURE_INVALID":
        return _screening_halt(
            target_id=target_id,
            status="INFRASTRUCTURE_INVALID",
            ledger=ledger,
            representation=representation,
            rankings=rankings,
            pair_lock=pair_lock,
            pair_review=review,
        )
    if pair_safety["status"] != "PASS" or review["decision"] != "ACCEPT":
        return _screening_halt(
            target_id=target_id,
            status="REJECT",
            ledger=ledger,
            representation=representation,
            rankings=rankings,
            pair_lock=pair_lock,
            pair_review=review,
        )
    irrelevant, irrelevant_record, irrelevant_lock = select_irrelevant_memory_v3(
        representation,
        relevant,
        prepared_entries,
        target_b_date_utc=target_b_date_utc,
        scope=scope,
        pair_safety_decision=pair_safety,
    )
    ledger.record(
        "IRRELEVANT_MEMORY_SELECTION", irrelevant_record["status"], evidence=irrelevant_record
    )
    exact_irrelevant_timestamp = validate_locked_irrelevant_timestamp_v3(
        irrelevant_lock,
        prepared_entries,
        target_b_timestamp_epoch=target_b_timestamp_epoch,
    )
    ledger.record(
        "EXACT_IRRELEVANT_TIMESTAMP",
        exact_irrelevant_timestamp["status"],
        evidence=exact_irrelevant_timestamp,
    )
    if exact_irrelevant_timestamp["status"] != "PASS":
        return _screening_halt(
            target_id=target_id,
            status="REJECT",
            ledger=ledger,
            representation=representation,
            rankings=rankings,
            pair_lock=pair_lock,
            pair_review=review,
        )
    ledger.record("SCREENING_RESULT", "PASS", evidence=review)
    return {
        "schema": "cmpilot-confirmatory-screening-result-v3",
        "target_id": target_id,
        "status": "PASS",
        "target_representation": representation,
        "prepared_source_entries": prepared_entries,
        "rankings": rankings,
        "pair_lock": pair_lock,
        "exact_source_timestamp": exact_source_timestamp,
        "relevant_source": relevant,
        "pair_review": review,
        "irrelevant_source": irrelevant,
        "irrelevant_record": irrelevant_record,
        "irrelevant_lock": irrelevant_lock,
        "exact_irrelevant_timestamp": exact_irrelevant_timestamp,
        "attrition_ledger": ledger.as_dict(),
        "rank_2_fallback_attempted": False,
        "evaluated_model_inference": False,
    }


def _source_session(
    store: MemoryStore, *, entry: Mapping[str, Any], packet: bytes, suffix: str
) -> None:
    source_id = str(entry["source_id"])
    store.begin_source_session(source_id=source_id, session_id=f"v3-source-{suffix}")
    store.record_source_validation(
        source_id=source_id,
        source_build=entry["source_build"],
        source_task_test=entry["source_task_test"],
        artifact_hashes=entry["source_artifact_hashes"],
    )
    store.store_memory(source_id=source_id, packet=packet)
    store.end_source_session()


def run_design_c_mock_v3(
    screening: Mapping[str, Any], *, memory_root: Path
) -> dict[str, Any]:
    """Exercise all DESIGN_C lifecycle and logging paths without a model."""

    if screening.get("status") != "PASS":
        raise ConfirmatoryV3Error("DESIGN_C mock requires a passed screening result")
    target_id = str(screening["target_id"])
    target = screening["target_representation"]
    relevant = screening["relevant_source"]
    irrelevant = screening["irrelevant_source"]
    relevant_packet = render_memory_packet(relevant, target_id=target_id)
    irrelevant_packet = render_memory_packet(irrelevant, target_id=target_id)
    results: list[dict[str, Any]] = []
    for index, condition in enumerate(CONDITIONS, 1):
        store = MemoryStore(Path(memory_root) / condition.casefold(), condition=condition)
        packet: bytes | None
        entry: Mapping[str, Any] | None
        rankings: Sequence[Mapping[str, Any]]
        lock: Mapping[str, Any]
        lock_kind: str
        if condition == "NO_MEMORY":
            packet = None
            entry = None
            rankings = ()
            lock = {}
            lock_kind = "NONE"
        elif condition == "IRRELEVANT_CORRECT_MEMORY":
            packet = irrelevant_packet
            entry = irrelevant
            rankings = screening["irrelevant_record"]["candidate_rankings"]
            lock = screening["irrelevant_lock"]
            lock_kind = "IRRELEVANT_MATCH_V3"
        else:
            packet = relevant_packet
            entry = relevant
            rankings = screening["rankings"]
            lock = screening["pair_lock"]
            lock_kind = "PAIR_TOP_ONE_V3"
        if entry is not None and packet is not None:
            _source_session(store, entry=entry, packet=packet, suffix=str(index))
        target_session_id = f"v3-target-{index}"
        store.begin_target_session(target_id=target_id, session_id=target_session_id)
        delivered = None
        retrieval_event = None
        if entry is not None:
            delivered, retrieval_event = store.retrieve(
                retrieval_query=build_retrieval_query(target),
                candidate_rankings=rankings,
                selected_source_id=str(entry["source_id"]),
                selection_lock=lock,
                lock_kind=lock_kind,
            )
            if delivered != packet:
                raise ConfirmatoryV3Error("delivered memory differs from the locked packet")
        endpoint = mock_agent_endpoint(
            condition=condition, target_id=target_id, delivered_memory=delivered
        )
        endpoint_event = store.record_target_endpoint(endpoint)
        store.end_target_session()
        revalidation = (
            REVALIDATION_INSTRUCTION if condition.endswith("REVALIDATE") else None
        )
        budget = context_budget_record(
            condition=condition,
            task_text=str(target["task_statement"]),
            memory_packet=delivered,
            revalidation_instruction=revalidation,
        )
        events_payload = store.events_path.read_bytes()
        results.append(
            {
                "condition": condition,
                "target_id": target_id,
                "source_id": None if entry is None else entry["source_id"],
                "memory_packet_sha256": None
                if delivered is None
                else hashlib.sha256(delivered).hexdigest(),
                "memory_packet_bytes": 0 if delivered is None else len(delivered),
                "retrieval_event": retrieval_event,
                "endpoint_event": endpoint_event,
                "context_budget": budget,
                "event_log_sha256": hashlib.sha256(events_payload).hexdigest(),
                "event_log_bytes": len(events_payload),
                "evaluated_model_inference": False,
            }
        )
    budgets = {row["context_budget"]["post_ingestion_budget"] for row in results}
    return {
        "schema": "cmpilot-design-c-mock-v3",
        "target_id": target_id,
        "conditions": list(CONDITIONS),
        "results": results,
        "context_budget_parity": budgets == {16384},
        "post_ingestion_budget": 16384,
        "no_junk_padding": True,
        "selective_memory_truncation": False,
        "revalidation_instruction_sha256": hashlib.sha256(
            REVALIDATION_INSTRUCTION.encode("utf-8")
        ).hexdigest(),
        "complete_logging": all(row["event_log_bytes"] > 0 for row in results),
        "evaluated_model_inference": False,
        "status": "PASS"
        if len(results) == len(CONDITIONS) and budgets == {16384}
        else "FAIL",
    }


def run_development_end_to_end_v3(
    *,
    target_id: str,
    scope: TargetIdentityScope,
    workspace_reader: AuditedWorkspaceReader,
    frozen_source_entries: Sequence[Mapping[str, Any]],
    target_b_date_utc: str,
    target_b_timestamp_epoch: int,
    sealed_evidence_handle: SealedEvidenceHandle,
    memory_root: Path,
) -> dict[str, Any]:
    """Use production screening, then the deterministic no-model endpoint."""

    screening = screen_target_v3(
        target_id=target_id,
        scope=scope,
        workspace_reader=workspace_reader,
        frozen_source_entries=frozen_source_entries,
        target_b_date_utc=target_b_date_utc,
        target_b_timestamp_epoch=target_b_timestamp_epoch,
        sealed_evidence_handle=sealed_evidence_handle,
    )
    design_c = (
        run_design_c_mock_v3(screening, memory_root=memory_root)
        if screening["status"] == "PASS"
        else None
    )
    return {
        "schema": "cmpilot-development-end-to-end-v3",
        "target_id": target_id,
        "target_scope_purpose": scope.purpose,
        "screening": screening,
        "design_c_mock": design_c,
        "status": "PASS"
        if screening["status"] == "PASS" and design_c and design_c["status"] == "PASS"
        else screening["status"],
        "evaluated_model_inference": False,
    }
