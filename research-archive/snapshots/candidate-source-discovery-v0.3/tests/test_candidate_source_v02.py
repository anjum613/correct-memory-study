from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from cmpilot.candidate_source_v02 import (
    ASSIGNMENT_PATTERN,
    CANDIDATE_ID_PATTERN,
    PROTOCOL_VERSION,
    SOURCE_RECORD_ID_PATTERN,
    SourceBatchRejected,
    SourceProtocolError,
    SourceRecordRejected,
    advisory_repair_episodes,
    build_source_record,
    canonical_candidate_id,
    deduplication_decision,
    github_pull_request_episode,
    normalize_github_repository,
    parse_bugsinpy_metadata,
    source_record_id,
    validate_github_search_page,
    validate_specification_directory,
)


ROOT = Path(__file__).parents[1]
SPECIFICATION_DIRECTORY = (
    ROOT / "benchmark-selection/discovery/prospective-v0.2"
)
VALIDATOR = ROOT / "scripts/validate_candidate_source_v02.py"
V01 = ROOT / "benchmark-selection/discovery/prospective-v0.1"
V01_HASHES = {
    "repository-repair-tasks.json": (
        "2f3723a8d26335c228d1d2ec14832c5a7879b5d150bb2b76ebdf840c743b5d33"
    ),
    "security-advisory-repairs.json": (
        "b7a5af42037cd010ee29e023d7dad7436dd489df55c068020db358c629c32d09"
    ),
    "source-priority-deduplication.json": (
        "ed9be3ccabe1a1e778882814ffcff8720054d0bc84b996f7a7a54520de53d071"
    ),
    "trust-boundary-issues-prs.json": (
        "8d41d13bbe47f28750855797684bd009cc5bde42f4b2748a8b12e873c06ad15b"
    ),
}


def _repository(repository_id: int, name: str = "alpha") -> dict[str, object]:
    return {
        "id": repository_id,
        "owner": "fixture-owner",
        "name": name,
        "html_url": f"https://github.com/fixture-owner/{name}",
        "visibility": "public",
    }


def _pull_request(
    *, number: int = 7, base: str = "a", head: str = "b", merge: str = "c"
) -> dict[str, object]:
    return {
        "number": number,
        "merged": True,
        "base": {"sha": base * 40},
        "head": {"sha": head * 40},
        "merge_commit_sha": merge * 40,
    }


def _advisory(
    *,
    references: list[str],
    packages: tuple[str, ...] = ("Fixture_Package",),
) -> dict[str, object]:
    return {
        "id": "GHSA-fixture-0000-0000",
        "aliases": ["CVE-2026-1000"],
        "affected": [
            {"package": {"ecosystem": "PyPI", "name": package}}
            for package in packages
        ],
        "references": [{"type": "FIX", "url": url} for url in references],
    }


def _commit_resolution(
    repository_id: int,
    repair: str,
    *,
    parent: str = "a",
    repository_name: str = "alpha",
) -> dict[str, object]:
    return {
        "repository": _repository(repository_id, repository_name),
        "commit_sha": repair * 40,
        "parent_shas": [parent * 40],
    }


def _error_code(error: pytest.ExceptionInfo[SourceProtocolError]) -> str:
    return error.value.code


def _read_specification(name: str) -> dict[str, object]:
    value = json.loads((SPECIFICATION_DIRECTORY / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_v01_specifications_remain_byte_for_byte_unchanged() -> None:
    assert {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in V01.iterdir()
        if path.suffix == ".json"
    } == V01_HASHES


def test_v02_specifications_validate_offline() -> None:
    result = validate_specification_directory(SPECIFICATION_DIRECTORY)

    assert result == {
        "identity_fetch_performed": False,
        "network_accessed": False,
        "pass": True,
        "protocol_version": PROTOCOL_VERSION,
        "specification_file_count": 8,
        "treatment_results_consulted": False,
    }


def test_v02_validator_cli_is_offline_and_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(VALIDATOR)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["network_accessed"] is False
    assert report["identity_fetch_performed"] is False


def test_source_record_schema_separates_raw_records_from_candidates() -> None:
    schema = _read_specification("source-record.schema.json")
    properties = schema["properties"]
    assert isinstance(properties, dict)

    assert properties["disposition"]["enum"] == [  # type: ignore[index]
        "MATERIALIZED",
        "SOURCE_REJECTED",
    ]
    assert properties["source_record_id"]["pattern"] == (  # type: ignore[index]
        "^CMVP-SRC-02-[0-9a-f]{64}$"
    )
    definitions = schema["$defs"]
    assert isinstance(definitions, dict)
    assert definitions["candidate_link"]["properties"]["canonical_candidate_id"][  # type: ignore[index]
        "pattern"
    ] == "^CMVP-CAND-02-[0-9a-f]{64}$"


def test_identity_and_priority_rules_have_no_source_range_ceiling() -> None:
    protocol = _read_specification("protocol.json")
    priority = _read_specification("source-priority-deduplication.json")
    identities = protocol["identity_rules"]
    semantics = priority["source_priority_semantics"]
    assert isinstance(identities, dict)
    assert isinstance(semantics, dict)

    assert identities["source_record_id"]["record_ceiling"] is None  # type: ignore[index]
    assert identities["canonical_candidate_id"]["record_ceiling"] is None  # type: ignore[index]
    assert identities["canonical_candidate_id"]["renumber_on_later_source"] is False  # type: ignore[index]
    assert "scientific score" in semantics["does_not_affect"]  # type: ignore[operator]
    assert "selection" in semantics["does_not_affect"]  # type: ignore[operator]


def test_bugsinpy_specification_forbids_executable_metadata() -> None:
    specification = _read_specification("repository-repair-tasks.json")
    grammar = specification["metadata_grammar"]
    materialization = specification["materialization"]
    assert isinstance(grammar, dict)
    assert isinstance(materialization, dict)

    assert grammar["assignment_regex"] == ASSIGNMENT_PATTERN.pattern
    assert {"shell execution", "eval", "command substitution"} <= set(
        grammar["evaluation_prohibitions"]  # type: ignore[arg-type]
    )
    assert materialization["semantic_bug_suitability_inspected"] is False


def test_advisory_specification_freezes_predicates_and_episode_unit() -> None:
    specification = _read_specification("security-advisory-repairs.json")
    filters = specification["filters"]
    multi_package = specification["multi_package_rules"]
    assert isinstance(filters, dict)
    assert isinstance(multi_package, dict)

    assert "absent or JSON null" in filters["withdrawn_predicate"]["active_if"]  # type: ignore[index,operator]
    assert "database_specific.malware is exactly true" in filters["malware_predicate"]["true_if"]  # type: ignore[index,operator]
    assert "distinct canonical repository numeric ID" in multi_package[
        "candidate_expansion"
    ]
    assert specification["candidate_unit"] == (
        "one advisory times one canonical GitHub repository repair episode"
    )


def test_all_eight_github_queries_retain_static_scope_and_order() -> None:
    specification = _read_specification("trust-boundary-issues-prs.json")
    queries = specification["queries"]
    pagination = specification["pagination"]
    assert isinstance(queries, list)
    assert isinstance(pagination, dict)

    assert [query["query_id"] for query in queries] == [
        f"TB-Q{position:02d}" for position in range(1, 9)
    ]
    assert [query["object_type"] for query in queries] == [
        "ISSUE",
        "PULL_REQUEST",
    ] * 4
    assert [query["open_closed_state"] for query in queries] == [
        "closed",
        "merged",
    ] * 4
    assert all(query["repository_constraint"] == "NONE" for query in queries)
    assert all(query["language"] == "Python" for query in queries)
    assert all(query["archive_behavior"] == "archived:false" for query in queries)
    assert all("UNCONSTRAINED" in query["fork_behavior"] for query in queries)
    assert all("is:public" in query["query"] for query in queries)
    assert pagination["per_page"] == 100
    assert pagination["result_cap"] == 1000
    assert pagination["sort"] == "created"
    assert pagination["order"] == "asc"


@pytest.mark.parametrize(
    ("metadata", "code"),
    [
        (
            "buggy_commit_id='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'\n"
            "fixed_commit_id=$(command)\n",
            "BUGSINPY_MALFORMED_LINE",
        ),
        (
            "buggy_commit_id='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'\n"
            "unknown_field='value'\n"
            "fixed_commit_id='bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'\n",
            "BUGSINPY_UNKNOWN_FIELD",
        ),
        (
            "buggy_commit_id='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'\n"
            "buggy_commit_id='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'\n"
            "fixed_commit_id='bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'\n",
            "BUGSINPY_DUPLICATE_FIELD",
        ),
        (
            "buggy_commit_id='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'\n",
            "BUGSINPY_REQUIRED_FIELD_MISSING",
        ),
    ],
)
def test_malformed_bugsinpy_metadata_is_rejected(
    metadata: str, code: str
) -> None:
    with pytest.raises(SourceRecordRejected) as error:
        parse_bugsinpy_metadata(metadata)

    assert _error_code(error) == code


def test_safe_bugsinpy_metadata_is_parsed_without_evaluation() -> None:
    values = parse_bugsinpy_metadata(
        "# fixed fixture\n"
        "buggy_commit_id = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'\n"
        "fixed_commit_id = \"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\"\n"
        "python_version = 3.11\n"
    )

    assert values == {
        "buggy_commit_id": "a" * 40,
        "fixed_commit_id": "b" * 40,
        "python_version": "3.11",
    }


def test_missing_repository_fields_prevent_materialization() -> None:
    repository = _repository(101)
    del repository["id"]

    with pytest.raises(SourceRecordRejected) as error:
        normalize_github_repository(repository)

    assert _error_code(error) == "GITHUB_REPOSITORY_ID_MISSING"


def test_multi_package_same_repository_advisory_collapses_to_one_episode() -> None:
    repair_url = f"https://github.com/fixture-owner/alpha/commit/{'c' * 40}"
    advisory = _advisory(
        references=[repair_url], packages=("Alpha_Package", "beta.package")
    )

    episodes = advisory_repair_episodes(
        advisory,
        advisory_path="advisories/github-reviewed/fixture.json",
        resolved_references={repair_url: _commit_resolution(101, "c")},
    )

    assert len(episodes) == 1
    assert episodes[0]["package_names"] == ["alpha-package", "beta-package"]


def test_multi_package_different_repository_advisory_preserves_episodes() -> None:
    first_url = f"https://github.com/fixture-owner/alpha/commit/{'c' * 40}"
    second_url = f"https://github.com/fixture-owner/beta/commit/{'d' * 40}"
    advisory = _advisory(
        references=[first_url, second_url],
        packages=("Alpha_Package", "beta.package"),
    )

    episodes = advisory_repair_episodes(
        advisory,
        advisory_path="advisories/github-reviewed/fixture.json",
        resolved_references={
            first_url: _commit_resolution(101, "c"),
            second_url: _commit_resolution(
                202, "d", parent="b", repository_name="beta"
            ),
        },
    )

    assert [episode["github_repository_id"] for episode in episodes] == [101, 202]
    assert all(
        episode["package_names"] == ["alpha-package", "beta-package"]
        for episode in episodes
    )


def test_withdrawn_advisory_is_source_rejected() -> None:
    advisory = _advisory(references=[])
    advisory["withdrawn"] = "2026-01-01T00:00:00Z"

    with pytest.raises(SourceRecordRejected) as error:
        advisory_repair_episodes(
            advisory,
            advisory_path="advisories/github-reviewed/fixture.json",
            resolved_references={},
        )

    assert _error_code(error) == "ADVISORY_WITHDRAWN"


@pytest.mark.parametrize(
    ("path", "database_specific"),
    [
        ("advisories/malware/fixture.json", {}),
        ("advisories/github-reviewed/fixture.json", {"malware": True}),
    ],
)
def test_malware_advisory_is_source_rejected(
    path: str, database_specific: dict[str, bool]
) -> None:
    advisory = _advisory(references=[])
    advisory["database_specific"] = database_specific

    with pytest.raises(SourceRecordRejected) as error:
        advisory_repair_episodes(
            advisory,
            advisory_path=path,
            resolved_references={},
        )

    assert _error_code(error) == "ADVISORY_MALWARE"


def test_commit_linked_advisory_uses_only_parent_as_snapshot() -> None:
    repair_url = f"https://github.com/fixture-owner/alpha/commit/{'c' * 40}"

    episode = advisory_repair_episodes(
        _advisory(references=[repair_url]),
        advisory_path="advisories/github-reviewed/fixture.json",
        resolved_references={repair_url: _commit_resolution(101, "c")},
    )[0]

    assert episode["candidate_snapshot_commit_sha"] == "a" * 40
    assert episode["repair_commit_sha"] == "c" * 40
    assert episode["pull_request_numbers"] == []


def test_pr_linked_advisory_uses_base_and_merge_shas() -> None:
    repair_url = "https://github.com/fixture-owner/alpha/pull/7"

    episode = advisory_repair_episodes(
        _advisory(references=[repair_url]),
        advisory_path="advisories/github-reviewed/fixture.json",
        resolved_references={
            repair_url: {
                "repository": _repository(101),
                "pull_request": _pull_request(),
            }
        },
    )[0]

    assert episode["candidate_snapshot_commit_sha"] == "a" * 40
    assert episode["repair_commit_sha"] == "c" * 40
    assert episode["pull_request_numbers"] == [7]


def test_issue_and_direct_pr_records_deduplicate_to_same_repair_episode() -> None:
    direct_pr = github_pull_request_episode(_pull_request(), _repository(101))
    issue_resolved_pr = {
        "github_repository_id": 101,
        "pull_request_number": 7,
        "repair_commit_sha": "c" * 40,
    }

    assert deduplication_decision(direct_pr, issue_resolved_pr) == (
        "EXACT_DUPLICATE"
    )


def test_missing_dedup_fields_never_match_as_wildcards() -> None:
    left = {"github_repository_id": None, "repair_commit_sha": None}
    right = {"github_repository_id": 101, "repair_commit_sha": "c" * 40}

    assert deduplication_decision(left, right) == "DISTINCT"


def test_exact_duplicate_requires_positive_immutable_evidence() -> None:
    left = {"github_repository_id": 101, "repair_commit_sha": "c" * 40}
    right = {
        "github_repository_id": 101,
        "repair_commit_sha": "c" * 40,
        "pull_request_number": 7,
    }

    assert deduplication_decision(left, right) == "EXACT_DUPLICATE"


def test_weaker_overlap_is_preserved_as_possible_duplicate() -> None:
    left = {
        "repository_full_name": "Fixture-Owner/Alpha",
        "repair_commit_sha": "c" * 40,
    }
    right = {
        "repository_full_name": "fixture-owner/alpha",
        "github_repository_id": 101,
    }

    assert deduplication_decision(left, right) == "POSSIBLE_DUPLICATE"


def test_incomplete_github_search_response_fails_closed() -> None:
    with pytest.raises(SourceBatchRejected) as error:
        validate_github_search_page(
            {"total_count": 1, "incomplete_results": True, "items": [{}]}
        )

    assert _error_code(error) == "GITHUB_SEARCH_INCOMPLETE_RESULTS"


def test_candidate_id_is_stable_after_adding_another_source() -> None:
    original = canonical_candidate_id(
        repository_id=101, repair_commit_sha="c" * 40
    )
    unrelated_source_id = source_record_id(
        source_id="later-source",
        source_revision="d" * 40,
        source_native_identity={"position": 1001},
    )
    repeated = canonical_candidate_id(
        repository_id=101, repair_commit_sha="c" * 40
    )

    assert CANDIDATE_ID_PATTERN.fullmatch(original)
    assert SOURCE_RECORD_ID_PATTERN.fullmatch(unrelated_source_id)
    assert repeated == original


def test_source_record_disposition_separates_rejection_from_candidate() -> None:
    record_id = source_record_id(
        source_id="fixture-source",
        source_revision="a" * 40,
        source_native_identity={"item": 1},
    )
    rejected = build_source_record(
        record_id=record_id,
        source_id="fixture-source",
        source_revision={"kind": "GIT_COMMIT", "value": "a" * 40},
        source_native_identity={"item": 1},
        raw_artifact={
            "path": "raw/item.json",
            "sha256": "b" * 64,
            "media_type": "application/json",
            "captured_at_utc": "2026-08-13T00:00:00Z",
        },
        disposition="SOURCE_REJECTED",
        rejection_reason_codes=["SOURCE_OBJECT_MALFORMED"],
    )

    assert rejected["candidate_links"] == []
    assert rejected["disposition"] == "SOURCE_REJECTED"
    assert rejected["treatment_results_consulted"] is False


def test_materialized_source_record_requires_candidate_link() -> None:
    record_id = source_record_id(
        source_id="fixture-source",
        source_revision="a" * 40,
        source_native_identity={"item": 1},
    )

    with pytest.raises(SourceProtocolError) as error:
        build_source_record(
            record_id=record_id,
            source_id="fixture-source",
            source_revision={"kind": "GIT_COMMIT", "value": "a" * 40},
            source_native_identity={"item": 1},
            raw_artifact={"path": "raw/item.json", "sha256": "b" * 64},
            disposition="MATERIALIZED",
        )

    assert _error_code(error) == "SOURCE_DISPOSITION_INVALID"
