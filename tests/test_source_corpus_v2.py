from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from cmpilot.source_corpus_v2 import (
    PROTOCOL_ID,
    SourceCorpusV2Error,
    build_s2_universe,
    choose_corpus_target,
    corpus_breadth,
    discover_source_candidates,
    operation_classes_v2,
    parse_instance_repository_anchor,
    round_robin_candidates,
    source_only_partition_assessment,
)


ANCHOR_A = "1" * 40
ANCHOR_B = "2" * 40


def _write_fixture(root: Path) -> None:
    package = root / "demo"
    tests = root / "tests"
    package.mkdir()
    tests.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "paths.py").write_text(
        "def normalize_url(url):\n"
        "    return url.strip()\n\n"
        "def unused_number(value):\n"
        "    return value + 1\n",
        encoding="utf-8",
    )
    (tests / "test_paths.py").write_text(
        "from demo.paths import normalize_url\n\n"
        "def test_normalize_url():\n"
        "    assert normalize_url(' https://example.test ') == 'https://example.test'\n",
        encoding="utf-8",
    )


def test_s2_universe_uses_instance_ids_only_and_is_reproducible() -> None:
    ids = [f"owner__repo_{ANCHOR_A}", f"other__tool_{ANCHOR_B}", f"owner__repo_{ANCHOR_A}"]
    first = build_s2_universe(ids)
    second = build_s2_universe(reversed(ids))
    assert first == second
    assert len(first) == 2
    assert {row["repository_url"] for row in first} == {
        "https://github.com/owner/repo.git",
        "https://github.com/other/tool.git",
    }
    assert all(row["source_commit_rule"] == "STRICT_FIRST_PARENT" for row in first)


def test_instance_parser_rejects_non_metadata_or_malformed_values() -> None:
    parsed = parse_instance_repository_anchor(f"owner__repo_{ANCHOR_A}")
    assert parsed.anchor_commit == ANCHOR_A
    assert len(parsed.ordering_sha256) == 64
    with pytest.raises(SourceCorpusV2Error):
        parse_instance_repository_anchor("owner/repo")
    with pytest.raises(SourceCorpusV2Error):
        parse_instance_repository_anchor(f"owner/name/escape_{ANCHOR_A}")


def test_source_only_partition_is_assessed_but_never_materialized() -> None:
    ids = [f"owner__repo{index}_{index:040x}" for index in range(1, 11)]
    record = source_only_partition_assessment(ids)
    assert record["source_only_partition_used"] is False
    assert record["implemented_assignment"] is None
    assert record["candidate_specific_fields_read"] == ["instance_id"]
    expected = [
        value
        for value in sorted(ids)
        if int(hashlib.sha256(f"{PROTOCOL_ID}|{value}".encode()).hexdigest(), 16)
        % 5
        == 0
    ]
    assert record["hypothetical_source_only_count"] == len(expected)


def test_discovery_extracts_exact_real_source_and_test_bytes(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    result = discover_source_candidates(
        tmp_path,
        repository_url="https://github.com/example/demo.git",
        repository_commit=ANCHOR_A,
        tier="S2",
        excluded_paths=(),
    )
    assert result["target_side_inputs"] == []
    assert result["candidate_count"] == 1
    candidate = result["candidates"][0]
    assert candidate["source_symbol"] == "normalize_url"
    assert candidate["source_implementation_or_patch"] == (
        "def normalize_url(url):\n    return url.strip()\n"
    )
    assert candidate["source_task_description"].startswith("def test_normalize_url")
    assert candidate["source_task_provenance"]["kind"] == "UPSTREAM_TEST"
    assert candidate["mechanical_focal_safety_level"] == "C"
    assert candidate["mechanical_pstar"]["source_truth"] is True
    assert candidate["candidate_generation_uses_target"] is False
    assert "PATH_OR_URL_VALIDATION" in candidate["operation_class"]


def test_discovery_excludes_target_paths_and_nonassertion_tests(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    result = discover_source_candidates(
        tmp_path,
        repository_url="https://github.com/example/demo.git",
        repository_commit=ANCHOR_A,
        tier="S1",
        excluded_paths=("demo/paths.py",),
    )
    assert result["candidate_count"] == 0


def test_operation_ontology_has_multiple_nonweighted_classes() -> None:
    classes = operation_classes_v2(
        "validate URL path then decode bytes and write a file before timeout"
    )
    assert "PATH_OR_URL_VALIDATION" in classes
    assert "ENCODING_CANONICALIZATION" in classes
    assert "FILE_RESOURCE_IO" in classes
    assert "TIME_BOUNDARY" in classes
    assert operation_classes_v2("render HTML email template") == (
        "MARKUP_SERIALIZATION",
    )
    assert operation_classes_v2("render an anchor href link")[:2] == (
        "MARKUP_LINK_SERIALIZATION",
        "MARKUP_SERIALIZATION",
    )


def test_round_robin_is_deterministic_and_outcome_independent() -> None:
    discoveries = [
        {
            "tier": "S1",
            "repository_url": "https://github.com/b/b.git",
            "repository_commit": ANCHOR_B,
            "candidates": [{"source_id": "b1"}, {"source_id": "b2"}],
        },
        {
            "tier": "S1",
            "repository_url": "https://github.com/a/a.git",
            "repository_commit": ANCHOR_A,
            "candidates": [{"source_id": "a1"}, {"source_id": "a2"}],
        },
    ]
    assert [row["source_id"] for row in round_robin_candidates(discoveries)] == [
        "a1",
        "b1",
        "a2",
        "b2",
    ]


def test_round_robin_respects_frozen_s2_hash_order() -> None:
    discoveries = [
        {
            "tier": "S2",
            "repository_url": "https://github.com/a/a.git",
            "repository_commit": ANCHOR_A,
            "repository_order_sha256": "f" * 64,
            "candidates": [{"source_id": "later"}],
        },
        {
            "tier": "S2",
            "repository_url": "https://github.com/z/z.git",
            "repository_commit": ANCHOR_B,
            "repository_order_sha256": "0" * 64,
            "candidates": [{"source_id": "earlier"}],
        },
    ]
    assert [row["source_id"] for row in round_robin_candidates(discoveries)] == [
        "earlier",
        "later",
    ]


def test_frozen_cost_rule_selects_50_under_reviewer_envelope() -> None:
    decision = choose_corpus_target(
        pilot_total_wall_seconds=20,
        pilot_qualified_count=10,
        materialization_gib=1,
    )
    assert decision["selected_target"] == 50
    assert decision["resource_envelope_satisfied"] is True
    assert decision["projections"][0]["feasible"] is True
    assert decision["projections"][1]["feasible"] is False


def test_breadth_fails_closed_until_all_three_floors_hold() -> None:
    entries = [
        {
            "repository_url": f"https://github.com/o/r{index}.git",
            "source_tier": "S2" if index < 2 else "S1",
            "operation_class": [f"OP{index}"],
        }
        for index in range(8)
    ]
    assert corpus_breadth(entries)["pass"] is True
    assert corpus_breadth(entries[:5])["pass"] is False
