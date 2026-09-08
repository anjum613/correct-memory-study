from __future__ import annotations

import json
from pathlib import Path
import subprocess

from cmpilot.source_corpus_v2 import SUCCESSOR_PROTOCOL_COMMIT
from cmpilot.source_validation import corpus_manifest_hash, validate_source_entry


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "artifacts/context-dependent-memory-source-pairing-v2"
PROTOCOL_STEM = "context-dependent-memory-source-pairing-development-v2"


def _load(name: str) -> dict:
    return json.loads((ARTIFACT_ROOT / name).read_text(encoding="utf-8"))


def test_successor_protocol_is_immutable_and_was_copied_exactly() -> None:
    for suffix in ("md", "json"):
        path = ROOT / f"protocols/{PROTOCOL_STEM}.{suffix}"
        frozen = subprocess.run(
            ["git", "show", f"{SUCCESSOR_PROTOCOL_COMMIT}:protocols/{PROTOCOL_STEM}.{suffix}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout
        assert path.read_bytes() == frozen
        assert (ARTIFACT_ROOT / f"successor-protocol.{suffix}").read_bytes() == frozen


def test_expanded_corpus_is_reproducible_correct_and_focal_safe() -> None:
    manifest = _load("expanded-source-corpus-manifest.json")
    validation = _load("source-validation-summary.json")
    assert manifest["source_corpus_entries"] == 50
    assert manifest["source_corpus_reproducible"] is True
    assert manifest["breadth"]["pass"] is True
    assert corpus_manifest_hash(manifest["entries"]) == manifest["source_corpus_sha256"]
    assert validation["source_build_pass_count"] == 50
    assert validation["source_task_test_pass_count"] == 50
    assert validation["source_focal_safe_count"] == 50
    for entry in manifest["entries"]:
        validate_source_entry(entry, confirmatory=True)


def test_source_only_partition_was_not_used() -> None:
    universe = _load("source-universe-design.json")
    assessment = universe["partition_assessment"]
    assert assessment["source_only_partition_used"] is False
    assert assessment["decision"] == "NOT_USED"
    assert assessment["implemented_assignment"] is None
    assert assessment["candidate_specific_fields_read"] == ["instance_id"]


def test_rankings_are_threshold_free_timestamp_valid_top_one_locks() -> None:
    design = _load("matcher-v2-design.json")
    rankings = _load("matcher-v2-development-rankings.json")
    assert design["global_similarity_threshold_required"] is False
    assert design["combined_or_weighted_score"] is None
    assert design["numerical_ambiguity_margin"] is None
    assert rankings["b_only"] is True
    assert rankings["top_one"] is True
    assert rankings["rank_2_fallback"] is False
    assert len(rankings["targets"]) == 5
    for target in rankings["targets"]:
        lock = target["selection_lock"]
        assert lock["top_one"] is True
        assert lock["rank_2_fallback"] is False
        assert lock["global_similarity_threshold"] is None
        assert target["sealed_exact_timestamp_validation"]["status"] == "PASS"


def test_ambiguity_and_firewall_are_ready_without_unseen_access() -> None:
    ambiguity = _load("ambiguity-policy.json")
    firewall = _load("oracle-firewall-v2.json")
    assert ambiguity["status"] == "PASS"
    assert ambiguity["numerical_margin"] is None
    assert all(row["accepted_for_lock"] for row in ambiguity["results"])
    pairing = firewall["pairing_side"]
    assert pairing["unseen_target_rows_read"] == 0
    assert pairing["unseen_u_r_security_artifacts_read"] == 0
    assert pairing["evaluated_model_outputs_read"] == 0
    assert firewall["status"] == "PASS"


def test_irrelevant_selector_is_nearest_eligible_without_fixed_window() -> None:
    control = _load("irrelevant-control-v2.json")
    selected = next(
        row
        for row in control["candidate_rankings"]
        if row["source_id"] == control["selected_source_id"]
    )
    eligible = [row for row in control["candidate_rankings"] if row["hard_gate_pass"]]
    assert selected["rank"] == 1
    assert selected["deltas"]["packet_token_absolute_difference"] == min(
        row["deltas"]["packet_token_absolute_difference"] for row in eligible
    )
    assert selected["operation_class_disjoint"] is True
    assert control["fixed_length_tolerance"] is None
    assert control["sealed_exact_timestamp_validation"]["status"] == "PASS"
