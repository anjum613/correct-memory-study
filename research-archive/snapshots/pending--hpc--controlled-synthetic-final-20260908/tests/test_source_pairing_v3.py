from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from cmpilot.source_pairing_v3 import (
    SourcePairingV3Error,
    enforce_irrelevant_lock_v3,
    enforce_top_source_lock_v3,
    matcher_design_record_v3,
    rank_sources_v3,
    select_irrelevant_memory_v3,
    select_top_source_v3,
    validate_locked_irrelevant_timestamp_v3,
    validate_locked_source_timestamp_v3,
)
from cmpilot.target_identity_v3 import TargetIdentityScope


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "artifacts/context-dependent-memory-source-pairing-v2"


def _load(name: str) -> dict:
    return json.loads((ARTIFACT_ROOT / name).read_text(encoding="utf-8"))


def _development_case(prefix: str) -> tuple[dict, list[dict], int, str]:
    target_row = next(
        row
        for row in _load("matcher-v2-development-rankings.json")["targets"]
        if row["target_id"].startswith(prefix)
    )
    representation = next(
        row["representation"]
        for row in _load("../context-dependent-memory-source-pairing/b-only-representation-results.json")[
            "results"
        ]
        if row["target_id"] == target_row["target_id"]
    )
    entries = _load("expanded-source-corpus-manifest.json")["entries"]
    epoch = int(target_row["target_b_timestamp_epoch"])
    day = datetime.fromtimestamp(epoch, timezone.utc).date().isoformat()
    return representation, entries, epoch, day


def test_pre_lock_matcher_uses_source_correct_not_historical_focal_level() -> None:
    target, entries, _, day = _development_case("buildbot__")
    scope = TargetIdentityScope.development_fixtures()
    rows = rank_sources_v3(target, entries, target_b_date_utc=day, scope=scope)
    assert len(rows) == 50
    assert matcher_design_record_v3()["pre_lock_focal_safety_annotation_used"] is False
    assert all(row["focal_safety_evaluated_pre_lock"] is False for row in rows)
    top = next(row for row in rows if row["hard_gate_pass"])
    top_entry = next(entry for entry in entries if entry["source_id"] == top["source_id"])
    assert top_entry["focal_source_safety"]["level"] == "C"


def test_v3_top_one_lock_is_deterministic_and_has_no_rank2_fallback() -> None:
    target, entries, epoch, day = _development_case("wagtail__")
    scope = TargetIdentityScope.development_fixtures()
    rankings, lock = select_top_source_v3(
        target, entries, target_b_date_utc=day, scope=scope
    )
    reversed_rankings, reversed_lock = select_top_source_v3(
        target, list(reversed(entries)), target_b_date_utc=day, scope=scope
    )
    assert rankings == reversed_rankings
    assert lock == reversed_lock
    assert lock["top_source_id"] == "src-wagtail-document-link-expand"
    enforce_top_source_lock_v3(lock, lock["top_source_id"])
    rank_two = next(
        row["source_id"]
        for row in rankings
        if row["hard_gate_pass"] and row["source_id"] != lock["top_source_id"]
    )
    with pytest.raises(PermissionError, match="rank-2"):
        enforce_top_source_lock_v3(lock, rank_two)
    timestamp = validate_locked_source_timestamp_v3(
        lock, entries, target_b_timestamp_epoch=epoch
    )
    assert timestamp["status"] == "PASS"
    assert timestamp["fallback_attempted"] is False


def test_generic_irrelevant_control_keeps_nearest_top_one_rule() -> None:
    target, entries, epoch, day = _development_case("wagtail__")
    scope = TargetIdentityScope.development_fixtures()
    _, pair_lock = select_top_source_v3(
        target, entries, target_b_date_utc=day, scope=scope
    )
    relevant = next(
        entry for entry in entries if entry["source_id"] == pair_lock["top_source_id"]
    )
    pair_safety = {
        "status": "PASS",
        "top_source_id": relevant["source_id"],
    }
    selected, record, lock = select_irrelevant_memory_v3(
        target,
        relevant,
        entries,
        target_b_date_utc=day,
        scope=scope,
        pair_safety_decision=pair_safety,
    )
    assert record["status"] == "PASS"
    assert selected["source_id"] == "src-aio-fernet-save-session"
    assert record["fixed_length_tolerance"] is None
    assert record["padding_or_truncation"] is False
    selected_row = next(
        row for row in record["candidate_rankings"] if row["source_id"] == selected["source_id"]
    )
    assert selected_row["rank"] == 1
    assert selected_row["source_side_a_or_b_safety"] is True
    enforce_irrelevant_lock_v3(lock, selected["source_id"])
    alternative = next(
        row["source_id"]
        for row in record["candidate_rankings"]
        if row["source_id"] != selected["source_id"]
    )
    with pytest.raises(PermissionError, match="rank-2"):
        enforce_irrelevant_lock_v3(lock, alternative)
    exact = validate_locked_irrelevant_timestamp_v3(
        lock, entries, target_b_timestamp_epoch=epoch
    )
    assert exact["status"] == "PASS"
    assert exact["fallback_attempted"] is False


def test_irrelevant_control_requires_passed_pair_specific_safety() -> None:
    target, entries, _, day = _development_case("wagtail__")
    relevant = next(
        entry for entry in entries if entry["source_id"] == "src-wagtail-document-link-expand"
    )
    with pytest.raises(SourcePairingV3Error, match="pair safety"):
        select_irrelevant_memory_v3(
            target,
            relevant,
            entries,
            target_b_date_utc=day,
            scope=TargetIdentityScope.development_fixtures(),
            pair_safety_decision={"status": "SOURCE_SAFETY_INSUFFICIENT"},
        )
