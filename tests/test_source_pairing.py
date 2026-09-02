from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from cmpilot.source_pairing import (
    CUE_TAXONOMY,
    PSTAR_ONTOLOGY,
    AuditedWorkspaceReader,
    PairingReadDenied,
    SourcePairingError,
    build_b_only_representation,
    calibrate_threshold,
    classify_task_statement,
    enforce_top_source_lock,
    extract_python_symbol,
    hash_vector,
    rank_sources,
    sealed_validation_request,
    select_top_source,
    source_feature_record,
    stable_record_hash,
    validate_b_only_mapping,
    validate_pstar,
    validate_sealed_response,
)
from cmpilot.susvibes_feasibility import DEVELOPMENT_IDS, SUSVIBES_REVISION


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ROOT = ROOT / "targets/public/susvibes-development"


def _workspace(tmp_path: Path, instance_id: str, task: str, code: str) -> Path:
    root = tmp_path / instance_id
    repository = root / "repository/pkg"
    repository.mkdir(parents=True)
    (root / "task.md").write_text(task, encoding="utf-8")
    (root / "public-metadata.json").write_text(
        json.dumps(
            {
                "b_image_manifest_digest": "sha256:" + "1" * 64,
                "b_tree_sha256": "2" * 64,
                "benchmark_revision": SUSVIBES_REVISION,
                "image_name": "pinned-image",
                "instance_id": instance_id,
                "language": "python",
                "project": "example/project",
            }
        ),
        encoding="utf-8",
    )
    (repository / "module.py").write_text(code, encoding="utf-8")
    return root


def _target() -> dict:
    value = {
        "benchmark_instance_id": DEVELOPMENT_IDS[0],
        "benchmark_revision": SUSVIBES_REVISION,
        "b_snapshot_sha256": "a" * 64,
        "task_statement": "Resolve proxy configuration for an HTTP redirect.",
        "language": "python",
        "repository_visible_imports": ["urllib.parse.urlparse"],
        "repository_visible_libraries": ["urllib"],
        "repository_visible_api_calls": ["urlparse", "proxies.get"],
        "task_described_operation": "PROXY_CONFIGURATION",
        "visible_target_symbols": ["rebuild_proxies"],
        "types_and_data_roles": ["PATH_OR_URL", "PROXY"],
        "ast_structure": ["Call:2", "FunctionDef:1"],
        "operation_categories": ["PROXY_CONFIGURATION", "HTTP_REDIRECT"],
        "task_semantic_embedding": {
            "model": "deterministic-local-hash-vectorizer",
            "model_revision": "cmpilot-hash-vectorizer-64-v1",
            "vector": list(hash_vector("Resolve proxy configuration for an HTTP redirect.")),
        },
        "configuration_context": {},
    }
    validate_b_only_mapping(value)
    return value


def _entry(source_id: str, *, semantic_text: str, tier: str = "S2") -> dict:
    code = """def resolve_proxies(request, proxies):
    parsed = urlparse(request.url)
    return proxies.get(parsed.scheme)
"""
    features = source_feature_record(code, semantic_text)
    return {
        "source_id": source_id,
        "source_tier": tier,
        "language": "python",
        "commit_timestamp_epoch": 100,
        **features,
        "source_build": {"classification": "PASS"},
        "source_task_test": {"classification": "PASS"},
        "focal_source_safety": {"classification": "PASS", "level": "A"},
    }


def test_development_target_identity_remains_exact() -> None:
    protocol = json.loads(
        (
            ROOT
            / "protocols/context-dependent-memory-source-pairing-development-v1.json"
        ).read_text(encoding="utf-8")
    )
    assert tuple(protocol["development_targets"]) == DEVELOPMENT_IDS
    assert len(DEVELOPMENT_IDS) == 5
    assert protocol["permanently_excluded_from_confirmation"] is True


def test_task_cue_classifier_on_five_official_development_statements() -> None:
    observed = {}
    for instance_id in DEVELOPMENT_IDS:
        statement = (PUBLIC_ROOT / instance_id / "task.md").read_text(encoding="utf-8")
        result = classify_task_statement(statement)
        assert result["classification"] in CUE_TAXONOMY
        observed[instance_id] = result["classification"]
    assert observed[DEVELOPMENT_IDS[0]] == "NO_SECURITY_CUE"
    assert observed[DEVELOPMENT_IDS[1]] == "NO_SECURITY_CUE"
    assert observed[DEVELOPMENT_IDS[2]] == "NO_SECURITY_CUE"
    assert observed[DEVELOPMENT_IDS[3]] == "SAFE_IMPLEMENTATION_LEAKAGE"
    assert observed[DEVELOPMENT_IDS[4]] == "SAFE_IMPLEMENTATION_LEAKAGE"


def test_task_cue_classifier_rejects_each_direct_leakage_kind() -> None:
    cases = (
        "Implement runtime hardening for timing attack protection.",
        "Strip Proxy-Authorization and then add new authentication.",
        "The security test is tests/test_secret.py.",
        "Repair CVE-2026-12345.",
        "Use the value only if it is within the root.",
        "Prevent header injection attacks.",
    )
    for statement in cases:
        assert classify_task_statement(statement)["public_text_eligible"] is False


def test_pairing_reader_audits_allowed_and_denied_reads(tmp_path: Path) -> None:
    workspace = _workspace(
        tmp_path,
        DEVELOPMENT_IDS[0],
        "Implement `pkg.module` function `operation`.",
        "import json\n\ndef operation(value):\n    return json.loads(value)\n",
    )
    sealed = tmp_path / "oracle_sealed"
    sealed.mkdir()
    secret = sealed / "security-test.patch"
    secret.write_text("secret", encoding="utf-8")
    (workspace / "escape").symlink_to(secret)
    reader = AuditedWorkspaceReader(workspace)
    assert reader.read_text("task.md").startswith("Implement")
    with pytest.raises(PairingReadDenied):
        reader.read_text("../oracle_sealed/security-test.patch")
    with pytest.raises(PairingReadDenied):
        reader.read_text(str(secret))
    with pytest.raises(PairingReadDenied):
        reader.read_text("escape")
    assert [event["decision"] for event in reader.events].count("DENY") == 3
    assert all(event["sequence"] == index for index, event in enumerate(reader.events, 1))


def test_b_only_representation_reads_public_workspace_and_has_no_oracle_fields(
    tmp_path: Path,
) -> None:
    workspace = _workspace(
        tmp_path,
        DEVELOPMENT_IDS[0],
        "Implement `pkg.module` function `resolve_proxies` for redirect proxy URLs.",
        "from urllib.parse import urlparse\n\ndef resolve_proxies(url, proxies):\n    return proxies.get(urlparse(url).scheme)\n",
    )
    reader = AuditedWorkspaceReader(workspace)
    first = build_b_only_representation(reader)
    second = build_b_only_representation(AuditedWorkspaceReader(workspace))
    assert first == second
    assert first["benchmark_instance_id"] == DEVELOPMENT_IDS[0]
    assert first["operation_categories"][0] in {"HTTP_REDIRECT", "PROXY_CONFIGURATION"}
    assert first["configuration_context"]["b_code_available"] is True
    assert all(event["decision"] == "ALLOW" for event in reader.events)
    serialized = json.dumps(first).casefold()
    for term in ("golden_patch", "security_test", "cve_id", '"u":', '"r":'):
        assert term not in serialized


def test_b_only_mapping_rejects_unseen_and_oracle_fields() -> None:
    target = _target()
    unseen = copy.deepcopy(target)
    unseen["benchmark_instance_id"] = "unseen"
    with pytest.raises(SourcePairingError, match="non-development"):
        validate_b_only_mapping(unseen)
    leaked = copy.deepcopy(target)
    leaked["security_test"] = "secret"
    with pytest.raises(SourcePairingError, match="forbidden"):
        validate_b_only_mapping(leaked)


def test_exact_python_symbol_extraction_and_ambiguity() -> None:
    source = "# header\n\ndef first():\n    return 1\n\ndef second():\n    return 2\n"
    exact, start, end = extract_python_symbol(source, "second")
    assert exact == "def second():\n    return 2\n"
    assert (start, end) == (6, 7)
    with pytest.raises(SourcePairingError, match="uniquely"):
        extract_python_symbol("def same(): pass\ndef same(): pass\n", "same")


def test_timestamp_and_source_gates_precede_deterministic_ranking() -> None:
    target = _target()
    valid = _entry("valid", semantic_text=target["task_statement"])
    future = _entry("future", semantic_text=target["task_statement"])
    future["commit_timestamp_epoch"] = 101
    broken = _entry("broken", semantic_text=target["task_statement"])
    broken["source_task_test"] = {"classification": "FAIL"}
    rows = rank_sources(target, [future, broken, valid], target_timestamp=100)
    assert [row["source_id"] for row in rows] == ["valid", "broken", "future"]
    assert rows[0]["hard_gate_pass"] is True
    assert all(not row["hard_gate_pass"] for row in rows[1:])
    assert rank_sources(target, [future, broken, valid], target_timestamp=100) == rows


def test_top_one_lock_is_immutable_and_has_no_rank_two_fallback() -> None:
    target = _target()
    top = _entry("top", semantic_text=target["task_statement"], tier="S1")
    lower = _entry("lower", semantic_text="unrelated cache serialization", tier="S3")
    rankings, lock = select_top_source(
        target,
        [lower, top],
        target_timestamp=100,
        thresholds={"semantic_similarity": 0.1},
        ambiguity_margins={"semantic_similarity": 0.01},
    )
    assert rankings[0]["source_id"] == lock["top_source_id"] == "top"
    enforce_top_source_lock(lock, "top")
    with pytest.raises(PermissionError, match="fallback"):
        enforce_top_source_lock(lock, "lower")
    changed = dict(lock)
    changed["top_source_id"] = "lower"
    with pytest.raises(SourcePairingError, match="hash mismatch"):
        enforce_top_source_lock(changed, "lower")
    assert sealed_validation_request(lock) == {
        "target_id": DEVELOPMENT_IDS[0],
        "top_source_id": "top",
        "pair_hash": lock["pair_hash"],
    }


def test_ambiguity_is_rejected_before_source_id_tiebreak() -> None:
    target = _target()
    left = _entry("a", semantic_text=target["task_statement"])
    right = copy.deepcopy(left)
    right["source_id"] = "b"
    with pytest.raises(SourcePairingError, match="AMBIGUOUS"):
        select_top_source(
            target,
            [right, left],
            target_timestamp=100,
            thresholds={"semantic_similarity": 0.1},
            ambiguity_margins={"semantic_similarity": 0.01},
        )


def test_sealed_validator_cannot_return_alternative_source_advice() -> None:
    base = {
        "decision": "REJECT",
        "questions": {f"Q{number}": "NO" for number in range(1, 17)},
        "evidence_hashes": {"packet": "a" * 64},
        "pair_hash": "b" * 64,
    }
    validate_sealed_response(base)
    with pytest.raises(SourcePairingError, match="advice"):
        validate_sealed_response({**base, "alternative_source_id": "rank-2"})


def test_pstar_schema_requires_one_falsifiable_operational_proposition() -> None:
    value = {
        "ontology_class": "BOUNDS_LENGTH",
        "proposition": "Every index passed to lookup is less than initialized_count.",
        "observable_objects": ["index", "initialized_count"],
        "operation": "lookup",
        "quantifier_or_boundary": "for every call, 0 <= index < initialized_count",
        "verification_method": "executable boundary test",
        "source_truth": True,
        "target_truth": "UNJUSTIFIED",
    }
    validate_pstar(value)
    assert value["ontology_class"] in PSTAR_ONTOLOGY
    vague = dict(value)
    vague["proposition"] = "Input is trusted"
    vague["observable_objects"] = ["input"]
    with pytest.raises(SourcePairingError, match="operationally"):
        validate_pstar(vague)


def test_prospective_threshold_calibration_rule() -> None:
    separated = [
        {"semantic_similarity": 0.9, "label": "POSITIVE", "source_repository": "a"},
        {"semantic_similarity": 0.8, "label": "POSITIVE", "source_repository": "b"},
        {"semantic_similarity": 0.2, "label": "NEGATIVE", "source_repository": "c"},
    ]
    result = calibrate_threshold(separated, "semantic_similarity")
    assert result["freezeable"] is True
    assert result["accepted_positive_count"] == 2
    assert result["accepted_negative_count"] == 0
    not_separated = [
        {"semantic_similarity": 0.9, "label": "POSITIVE", "source_repository": "a"},
        {"semantic_similarity": 0.8, "label": "NEGATIVE", "source_repository": "c"},
    ]
    assert calibrate_threshold(not_separated, "semantic_similarity")["freezeable"] is False


def test_pair_lock_hash_is_deterministic() -> None:
    assert stable_record_hash({"b": 2, "a": 1}) == stable_record_hash({"a": 1, "b": 2})
