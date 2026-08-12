from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cmpilot.candidate_discovery import load_query, search_url


ROOT = Path(__file__).parents[1]
DISCOVERY = ROOT / "benchmark-selection/discovery/v0.1"
SNAPSHOT = DISCOVERY / "snapshots/github-python-2024-medium-001"
AUDIT = DISCOVERY / "audits/github-python-2024-medium-001-pagination.json"
PROSPECTIVE = ROOT / "benchmark-selection/discovery/prospective-v0.1"
SOURCE_HASH = "64d4e57420060938e45d1446a93c73b81538b536b211e9e709e465f7b41ddd68"
RAW_HASH = "72715ab82226cbfef052b494ad02b99ac34df4b62b67b3d09284883891676cfa"
CAPTURE_HASH = "a1d4e143a0efef9363d68de9e2da9f579da1e99e11702c44a514bd806817534d"
DISCOVERY_HASH = "6c0585196830bfeb593549944b2d2a8036abd7808b765ada8340f5c0c5ef5a59"
QUERY_HASH = "fac93e3b703dfc9692ae364352c3853384f56992a02b7fe9ece8b2556ce4e76c"


def _read(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_pagination_audit_is_derived_from_preserved_capture() -> None:
    audit = _read(AUDIT)
    query = load_query(DISCOVERY / "query.json")
    raw_path = SNAPSHOT / "raw/search.json"
    raw = _read(raw_path)
    capture = _read(SNAPSHOT / "capture-manifest.json")
    requests = capture["requests"]
    assert isinstance(requests, list)
    search_request = requests[0]
    assert isinstance(search_request, dict)

    assert raw["total_count"] == audit["total_count"] == 2420
    assert raw["incomplete_results"] is audit["incomplete_results"] is False
    assert len(raw["items"]) == audit["returned_item_count"] == 8  # type: ignore[arg-type]
    assert audit["total_count"] > audit["returned_item_count"]  # type: ignore[operator]
    assert audit["page"] == query["page"] == 1
    assert audit["per_page"] == query["per_page"] == 8
    assert audit["sort"] == query["sort"] == "stars"
    assert audit["order"] == query["order"] == "desc"
    assert audit["endpoint"] == query["endpoint"]
    assert audit["request_url"] == search_request["url"] == search_url(query)
    assert audit["api_version_requested"] == query["api_version"] == "2022-11-28"
    assert audit["api_version_selected"] == (
        search_request["response_headers"]["x-github-api-version-selected"]  # type: ignore[index]
    )
    assert audit["retrieved_at_utc"] == search_request["retrieved_at_utc"]
    assert audit["response_date_utc"] == "2026-08-12T14:54:04Z"
    assert audit["raw_search_response_sha256"] == _sha256(raw_path) == RAW_HASH
    assert audit["capture_manifest_sha256"] == _sha256(
        SNAPSHOT / "capture-manifest.json"
    ) == CAPTURE_HASH
    assert audit["discovery_manifest_sha256"] == _sha256(
        SNAPSHOT / "discovery-manifest.json"
    ) == DISCOVERY_HASH
    assert audit["query_sha256"] == _sha256(DISCOVERY / "query.json") == QUERY_HASH
    assert audit["source_list_sha256"] == _sha256(
        SNAPSHOT / "source-list.json"
    ) == SOURCE_HASH
    assert audit["treatment_results_consulted"] is False


def test_additional_source_specs_are_frozen_and_unexecuted() -> None:
    specifications = [
        _read(PROSPECTIVE / "repository-repair-tasks.json"),
        _read(PROSPECTIVE / "security-advisory-repairs.json"),
        _read(PROSPECTIVE / "trust-boundary-issues-prs.json"),
        _read(PROSPECTIVE / "source-priority-deduplication.json"),
    ]

    assert all(
        specification["execution_status"] == "FROZEN_NOT_EXECUTED"
        for specification in specifications
    )
    assert all(
        specification["protocol_version"] == "benchmark-selection-v0.1"
        for specification in specifications
    )
    assert all(
        specification["treatment_results_consulted"] is False
        for specification in specifications
    )
    assert sorted(path.name for path in PROSPECTIVE.iterdir()) == [
        "README.md",
        "repository-repair-tasks.json",
        "security-advisory-repairs.json",
        "source-priority-deduplication.json",
        "trust-boundary-issues-prs.json",
    ]


def test_repository_repair_source_has_exact_version_and_import_rules() -> None:
    specification = _read(PROSPECTIVE / "repository-repair-tasks.json")
    source = specification["source"]
    imports = specification["import_rules"]
    pagination = specification["pagination"]
    identifiers = specification["candidate_id_policy"]
    assert isinstance(source, dict)
    assert isinstance(imports, dict)
    assert isinstance(pagination, dict)
    assert isinstance(identifiers, dict)

    assert source["repository"] == "https://github.com/soarsmu/BugsInPy.git"
    assert source["resolved_ref"] == "refs/heads/master"
    assert source["revision"] == "11c5f1eea954a42132cfd06bf257766a7963e0fd"
    assert imports["include_every_match"] is True
    assert imports["metadata_only_first_pass"] is True
    assert imports["unsupported_or_missing_definition"].startswith("retain")
    assert pagination["tree_walk"] == "all matching paths at the pinned commit"
    assert identifiers["first_id"] == "CMVP-CAND-1001"
    assert identifiers["last_id"] == "CMVP-CAND-1999"


def test_security_source_has_exact_version_and_complete_import_policy() -> None:
    specification = _read(PROSPECTIVE / "security-advisory-repairs.json")
    source = specification["source"]
    filters = specification["filters"]
    imports = specification["import_rules"]
    assert isinstance(source, dict)
    assert isinstance(filters, dict)
    assert isinstance(imports, dict)

    assert source["repository"] == "https://github.com/github/advisory-database.git"
    assert source["resolved_ref"] == "refs/heads/main"
    assert source["revision"] == "bfef29f8e04ad5037181f98a990572d825dff579"
    assert filters["ecosystem"] == "PyPI"
    assert filters["malware_excluded"] is True
    assert imports["include_every_match"] is True
    assert "NEEDS_REVIEW" in imports["pull_request_resolution"]


def test_trust_boundary_searches_freeze_queries_and_pagination() -> None:
    specification = _read(PROSPECTIVE / "trust-boundary-issues-prs.json")
    api = specification["api"]
    pagination = specification["pagination"]
    queries = specification["queries"]
    assert isinstance(api, dict)
    assert isinstance(pagination, dict)
    assert isinstance(queries, list)

    assert api == {
        "accept": "application/vnd.github+json",
        "endpoint": "https://api.github.com/search/issues",
        "version": "2022-11-28",
    }
    assert pagination["first_page"] == 1
    assert pagination["per_page"] == 100
    assert pagination["maximum_pages"] == 10
    assert pagination["result_cap"] == 1000
    assert "fail closed" in pagination["total_count_over_cap"]
    assert len(queries) == 8
    assert [query["kind"] for query in queries] == [  # type: ignore[index]
        "ISSUE",
        "PULL_REQUEST",
    ] * 4
    assert len({query["trust_family_basis"] for query in queries}) == 4  # type: ignore[index]


def test_source_priority_resolves_identity_without_ranking() -> None:
    specification = _read(PROSPECTIVE / "source-priority-deduplication.json")

    assert specification["source_priority_high_to_low"] == [
        "SECURITY_ADVISORY_REPAIR",
        "REPOSITORY_REPAIR_BENCHMARK",
        "TRUST_BOUNDARY_ISSUE_PR_SEARCH",
        "GENERIC_REPOSITORY_DISCOVERY",
    ]
    assert specification["priority_is_not_ranking"] is True
    assert "not collapsed" in specification["generic_repository_rule"]
    assert specification["candidate_id_ranges"] == {
        "GENERIC_REPOSITORY_DISCOVERY": ["CMVP-CAND-0001", "CMVP-CAND-0999"],
        "REPOSITORY_REPAIR_BENCHMARK": ["CMVP-CAND-1001", "CMVP-CAND-1999"],
        "SECURITY_ADVISORY_REPAIR": ["CMVP-CAND-2001", "CMVP-CAND-2999"],
        "TRUST_BOUNDARY_ISSUE_PR_SEARCH": ["CMVP-CAND-3001", "CMVP-CAND-3999"],
    }
