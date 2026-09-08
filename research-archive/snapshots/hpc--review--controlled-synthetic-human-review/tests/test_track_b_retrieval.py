from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from cmpilot.track_b.core import (
    assert_independent_input, classify_security_category, extract_github_references,
    rank_and_deduplicate, scan_advisories, seed_from_advisory, validate_packet,
)
from cmpilot.track_b.github import commit_file_facts


ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "track_b" / "config-v0.1.json").read_text())


def advisory(advisory_id: str = "GHSA-aaaa-bbbb-cccc", ecosystem: str = "PyPI", cwe: str = "CWE-22", references: list[dict[str, str]] | None = None) -> dict[str, object]:
    return {
        "id": advisory_id, "aliases": ["CVE-2026-0001"],
        "summary": "Path traversal in archive extraction",
        "details": "A path traversal permits escape from the destination.",
        "published": "2026-01-01T00:00:00Z", "modified": "2026-01-02T00:00:00Z",
        "database_specific": {"cwe_ids": [cwe]},
        "affected": [{"package": {"ecosystem": ecosystem, "name": "demo"}}],
        "references": references or [{"type": "WEB", "url": "https://github.com/example/demo/commit/0123456789abcdef0123456789abcdef01234567"}],
    }


def test_github_reference_extraction() -> None:
    record = advisory(references=[
        {"type": "WEB", "url": "https://github.com/example/demo/pull/42"},
        {"type": "WEB", "url": "https://github.com/example/demo/issues/7"},
        {"type": "WEB", "url": "https://github.com/example/demo/commit/0123456789abcdef0123456789abcdef01234567"},
    ])
    result = extract_github_references(record)
    assert result["repository"] == "example/demo"
    assert result["commits"][0]["sha"] == "0123456789abcdef0123456789abcdef01234567"
    assert result["pulls"][0]["number"] == 42
    assert result["issues"][0]["number"] == 7


def test_supported_language_rejection() -> None:
    seed, reason = seed_from_advisory(advisory(ecosystem="RubyGems"), "a.json", "a" * 40, CONFIG)
    assert seed is None
    assert reason == "UNSUPPORTED_LANGUAGE"


def test_security_category_mapping_prefers_ordered_cwe_rule() -> None:
    category, evidence = classify_security_category(advisory(cwe="CWE-918"), CONFIG["security_categories"])
    assert category == "NETWORK_DESTINATION_SSRF"
    assert evidence["cwes"] == ["CWE-918"]


def test_duplicate_removal_keeps_lexicographically_first_advisory() -> None:
    first, _ = seed_from_advisory(advisory("GHSA-aaaa-aaaa-aaaa"), "a.json", "a" * 40, CONFIG)
    second, _ = seed_from_advisory(advisory("GHSA-zzzz-zzzz-zzzz"), "z.json", "a" * 40, CONFIG)
    assert first is not None and second is not None
    ranked, duplicates = rank_and_deduplicate([second, first])
    assert duplicates == 1
    assert [item["advisory_id"] for item in ranked] == ["GHSA-aaaa-aaaa-aaaa"]


def test_seed_ordering_and_ranking_are_stable(tmp_path: Path) -> None:
    root = tmp_path / "advisories"
    root.mkdir()
    low = advisory("GHSA-0000-0000-0001", references=[{"type": "PACKAGE", "url": "https://github.com/example/low"}])
    high = advisory("GHSA-9999-9999-9999", references=[
        {"type": "WEB", "url": "https://github.com/example/high/commit/0123456789abcdef0123456789abcdef01234567"},
        {"type": "WEB", "url": "https://github.com/example/high/pull/9"},
    ])
    (root / "z.json").write_text(json.dumps(low))
    (root / "a.json").write_text(json.dumps(high))
    ranked_one, _ = scan_advisories(root, CONFIG, "a" * 40)
    ranked_two, _ = scan_advisories(root, CONFIG, "a" * 40)
    assert [item["advisory_id"] for item in ranked_one] == ["GHSA-9999-9999-9999", "GHSA-0000-0000-0001"]
    assert ranked_one == ranked_two


def test_packet_required_fields() -> None:
    packet = {
        "seed_id": "GHSA-a", "advisory_id": "GHSA-a", "advisory_source_revision": "a" * 40,
        "repository": "example/demo", "language": "Python", "security_category": "FILESYSTEM_PATH_ARCHIVE",
        "fix_anchor": {"commit": None, "PR": None, "issue": None, "date": None, "affected_files": [], "source_files": [], "test_files": []},
        "relationships": [], "historical_changes": [], "test_infrastructure": {}, "raw_evidence": [],
        "unresolved_fields": [], "history_assessment": "NO_USEFUL_HISTORY",
    }
    validate_packet(packet)
    invalid = copy.deepcopy(packet)
    del invalid["fix_anchor"]["source_files"]
    with pytest.raises(ValueError, match="source_files"):
        validate_packet(invalid)


def test_commit_file_facts_enforces_supported_source_and_detects_tests() -> None:
    facts = commit_file_facts({"files": [
        {"filename": "src/app.py", "additions": 4, "deletions": 1},
        {"filename": "tests/test_app.py", "additions": 5, "deletions": 0},
        {"filename": "native/helper.cc", "additions": 20, "deletions": 2},
    ]}, CONFIG)
    assert facts["source_files"] == ["src/app.py"]
    assert facts["test_files"] == ["tests/test_app.py"]
    assert facts["languages"] == ["Python"]
    assert facts["additions"] == 29


@pytest.mark.parametrize("path", [
    "/home/anjum/Documents/research/correct-memory-study-worktrees/candidate-screening-v020-hybrid",
    "/home/anjum/Documents/research/correct-memory-study-worktrees/candidate-screening-v020-hybrid/anything.json",
    "/safe/root/sealed_queue/input.jsonl",
    "/safe/root/tasks/demo/hidden_oracles/witness.py",
])
def test_track_a_and_protected_paths_are_never_seed_inputs(path: str) -> None:
    with pytest.raises(ValueError):
        assert_independent_input(Path(path), CONFIG)
