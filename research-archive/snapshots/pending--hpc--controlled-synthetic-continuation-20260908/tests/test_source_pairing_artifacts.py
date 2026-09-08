from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cmpilot.pair_review import PAIR_REVIEW_QUESTIONS, validate_review_request
from cmpilot.source_pairing import (
    CUE_TAXONOMY,
    PSTAR_ONTOLOGY,
    classify_task_statement,
    enforce_top_source_lock,
    rank_sources,
    stable_record_hash,
    validate_b_only_mapping,
    validate_pstar,
    validate_sealed_response,
)
from cmpilot.source_validation import (
    corpus_manifest_hash,
    validate_source_entry,
    validate_timestamp,
)
from cmpilot.susvibes_feasibility import DEVELOPMENT_IDS, SUSVIBES_REVISION, sha256_file


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "artifacts/context-dependent-memory-source-pairing"


def load(name: str) -> dict:
    return json.loads((ARTIFACT_ROOT / name).read_text(encoding="utf-8"))


def test_source_corpus_is_reconstructible_correct_and_focal_safe() -> None:
    manifest = load("source-corpus-manifest.json")
    spec_path = ROOT / manifest["source_spec_path"]
    assert manifest["susvibes_revision"] == SUSVIBES_REVISION
    assert manifest["source_spec_sha256"] == sha256_file(spec_path)
    assert manifest["source_corpus_entries"] == len(manifest["entries"]) == 12
    assert manifest["source_corpus_sha256"] == corpus_manifest_hash(manifest["entries"])
    assert manifest["arbitrary_live_search_used"] is False
    assert manifest["s4_enabled"] is False
    for entry in manifest["entries"]:
        validate_source_entry(entry, confirmatory=True)
        assert entry["source_build"]["classification"] == "PASS"
        assert entry["source_task_test"]["classification"] == "PASS"
        assert entry["source_test_result"] == "PASS"
        assert entry["focal_source_safety"]["scope"] == "FOCAL_SOURCE_SAFETY_NOT_GLOBAL_SECURITY"
        validate_pstar(entry["focal_source_safety"]["pstar"])
        assert hashlib.sha256(
            entry["source_implementation_or_patch"].encode("utf-8")
        ).hexdigest() == entry["source_artifact_hashes"]["source_implementation"]
        assert hashlib.sha256(entry["source_task_description"].encode("utf-8")).hexdigest() == entry["source_artifact_hashes"]["source_task"]
        target_times = entry["reconstruction"]["target_B_timestamps"]
        assert set(target_times) == set(DEVELOPMENT_IDS)
        for target_id in DEVELOPMENT_IDS:
            expected = entry["commit_timestamp_epoch"] <= target_times[target_id]["epoch"]
            assert entry["available_before_target_B"][target_id] is expected
            if expected:
                validate_timestamp(
                    entry["commit_timestamp_epoch"], target_times[target_id]["epoch"]
                )


def test_source_validation_retains_infrastructure_attrition() -> None:
    validation = load("source-validation-results.json")
    assert validation["qualified_count"] == 12
    assert validation["source_build_pass_count"] == 12
    assert validation["source_task_test_pass_count"] == 12
    assert len(validation["attrition"]) == 1
    attempts = validation["attrition"][0]["source_task_test_attempts"]
    assert [attempt["source_task_test"]["classification"] for attempt in attempts] == [
        "INFRASTRUCTURE_INVALID",
        "INFRASTRUCTURE_INVALID",
    ]
    assert "No module named pytest" in attempts[0]["source_task_test"]["stderr_utf8"]
    assert "NativeStringIO" in attempts[1]["source_task_test"]["stdout_utf8"]
    focal = load("source-focal-safety-results.json")
    assert focal["pass_count"] == 12
    assert focal["scope"] == "FOCAL_SOURCE_SAFETY_NOT_GLOBAL_SECURITY"


def test_task_cues_and_b_only_representations_are_exact_and_audited() -> None:
    cues = load("task-statement-cue-development.json")
    assert cues["task_statement_cue_rule_ready"] is True
    assert cues["sanitization_rule"] == "NONE"
    assert cues["eligible_count"] == 3
    assert cues["rejected_count"] == 2
    assert tuple(row["target_id"] for row in cues["results"]) == DEVELOPMENT_IDS
    for row in cues["results"]:
        observed = classify_task_statement(row["official_task_statement"])
        assert observed["classification"] == row["classification"]
        assert row["classification"] in CUE_TAXONOMY

    representations = load("b-only-representation-results.json")
    assert representations["all_reads_audited"] is True
    assert representations["oracle_fields_observed"] is False
    assert tuple(row["target_id"] for row in representations["results"]) == DEVELOPMENT_IDS
    for row in representations["results"]:
        validate_b_only_mapping(row["representation"])
        assert row["denied_read_count"] == 0
        assert row["filesystem_read_audit"]
        assert all(event["decision"] == "ALLOW" for event in row["filesystem_read_audit"])


def test_matcher_rankings_are_deterministic_and_lock_rank_one() -> None:
    manifest = load("source-corpus-manifest.json")
    representations = {
        row["target_id"]: row["representation"]
        for row in load("b-only-representation-results.json")["results"]
    }
    rankings = load("matcher-development-rankings.json")
    assert rankings["ranking_uses_target_oracle"] is False
    assert rankings["top_one"] is True
    assert rankings["rank_2_fallback"] is False
    for target in rankings["targets"]:
        observed = rank_sources(
            representations[target["target_id"]],
            manifest["entries"],
            target_timestamp=target["target_timestamp_epoch"],
        )
        assert observed == target["full_rankings"]
        selection = target["development_selection"]
        assert selection["status"] == "LOCKED"
        lock = selection["lock"]
        assert lock["top_source_id"] == observed[0]["source_id"]
        assert lock["source_corpus_sha256"] == manifest["source_corpus_sha256"]
        enforce_top_source_lock(lock, observed[0]["source_id"])
    thresholds = load("matcher-threshold-candidate.json")
    assert thresholds["matcher_thresholds_freezeable"] is False
    assert thresholds["decision"] == "DO_NOT_FREEZE_INADEQUATE_SEPARATION"


def test_pairing_oracle_firewall_and_sealed_review_are_one_way() -> None:
    firewall = load("oracle-firewall-audit.json")
    assert firewall["status"] == "PASS"
    assert firewall["network_isolated"] is True
    assert firewall["every_pairing_filesystem_read_uses_audited_reader"] is True
    assert tuple(case["target_id"] for case in firewall["cases"]) == DEVELOPMENT_IDS
    for case in firewall["cases"]:
        assert case["pass"] is True
        assert case["audited_reader_pass"] is True
        assert case["sandbox"]["pass"] is True
        assert all(case["audited_denial_checks"].values())

    reviews = load("pair-review-development-results.json")
    assert reviews["accepted_count"] == 1
    assert reviews["rejected_count"] == 4
    assert reviews["alternative_source_advice"] is False
    assert reviews["rank_2_fallback"] is False
    for result in reviews["results"]:
        validate_review_request(result["request"])
        validate_sealed_response(result["response"])
        assert result["request"]["pair_hash"] == result["response"]["pair_hash"]
        assert set(result["response"]["questions"]) == set(PAIR_REVIEW_QUESTIONS)
        assert set(result["response"]) == {
            "decision",
            "questions",
            "evidence_hashes",
            "pair_hash",
        }
    serialized = json.dumps(reviews).casefold()
    assert "alternative_source_id" not in serialized
    assert "rank_2_source" not in serialized


def test_pstar_ontology_candidate_preserves_all_frozen_classes() -> None:
    ontology = load("pstar-ontology-candidate.json")
    assert ontology["adequacy"] == "ADEQUATE_FOR_CANDIDATE_REVIEW"
    assert tuple(row["name"] for row in ontology["classes"]) == PSTAR_ONTOLOGY
    assert ontology["new_classes_added_after_development"] == []
    assert sum(row["development_source_count"] for row in ontology["classes"]) == 12


def test_b_only_and_source_schemas_cover_runtime_records() -> None:
    b_schema = json.loads(
        (ROOT / "schemas/b-only-target-representation.schema.json").read_text()
    )
    observed_fields = set(
        load("b-only-representation-results.json")["results"][0]["representation"]
    )
    assert set(b_schema["required"]) == observed_fields
    source_schema = load("source-corpus-schema.json")
    observed_source_fields = set(load("source-corpus-manifest.json")["entries"][0])
    assert set(source_schema["required"]) == observed_source_fields
