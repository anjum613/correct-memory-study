from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from cmpilot.candidate_source_v03 import (
    CANDIDATE_ID_PATTERN,
    FORBIDDEN_DISCOVERY_ASSIGNMENTS,
    PROTOCOL_VERSION,
    SOURCE_RECORD_ID_PATTERN,
    V02_HASHES,
    CandidateSourceV03Error,
    CreatedInterval,
    PartitionObservation,
    build_candidate_provenance_index,
    build_created_partition_plan,
    canonical_candidate_id,
    deduplication_decision,
    partition_query,
    raw_artifact_descriptor,
    request_decision,
    resolve_benchmark_episode,
    resolve_explicit_commit_episode,
    resolve_merged_pr_episode,
    source_record_id,
    split_created_interval,
    validate_v03_specification,
    verify_raw_artifact,
)


ROOT = Path(__file__).parents[1]
V02 = ROOT / "benchmark-selection/discovery/prospective-v0.2"
V03 = ROOT / "benchmark-selection/discovery/prospective-v0.3"
AUDIT = (
    ROOT
    / "benchmark-selection/discovery/audits/"
    "source-specification-v0.2-final-preexecution-audit.json"
)
VALIDATOR = ROOT / "scripts/validate_candidate_source_v03.py"
MODULE = ROOT / "src/cmpilot/candidate_source_v03.py"


def _read(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _code(error: pytest.ExceptionInfo[CandidateSourceV03Error]) -> str:
    return error.value.code


def _episode(
    *, repository: int = 101, snapshot: str = "a", repair: str = "c"
) -> dict[str, object]:
    return {
        "github_repository_id": repository,
        "candidate_snapshot_commit_sha": snapshot * 40,
        "repair_commit_sha": repair * 40,
    }


def test_v02_specifications_remain_byte_for_byte_unchanged() -> None:
    assert {
        name: hashlib.sha256((V02 / name).read_bytes()).hexdigest()
        for name in V02_HASHES
    } == V02_HASHES


def test_v03_additive_specification_validates_offline() -> None:
    result = validate_v03_specification(
        v02_directory=V02,
        v03_directory=V03,
        audit_path=AUDIT,
    )

    assert result == {
        "identity_fetch_performed": False,
        "network_accessed": False,
        "pass": True,
        "protocol_version": PROTOCOL_VERSION,
        "treatment_results_consulted": False,
        "v02_hash_count": 8,
        "v03_file_count": 4,
    }


def test_v03_validator_cli_has_no_source_execution() -> None:
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


def test_audit_is_fail_closed_and_records_no_access() -> None:
    audit = _read(AUDIT)
    checks = audit["checks"]
    assert isinstance(checks, list)

    assert audit["audited_commit"] == (
        "715592b8b96a689f7e532d5ad211bc9b5c7d82c1"
    )
    assert audit["result"] == "REQUIRES_PROSPECTIVE_AMENDMENT"
    assert all(check["result"] == "FAIL" for check in checks)
    assert audit["identity_fetch_performed"] is False
    assert audit["real_discovery_source_executed"] is False
    assert audit["experiment_accessed"] is False
    assert audit["treatment_results_consulted"] is False


def test_candidate_identity_includes_pre_repair_snapshot() -> None:
    first = canonical_candidate_id(
        repository_id=101,
        candidate_snapshot_commit_sha="a" * 40,
        repair_commit_sha="c" * 40,
    )
    different_branch = canonical_candidate_id(
        repository_id=101,
        candidate_snapshot_commit_sha="b" * 40,
        repair_commit_sha="c" * 40,
    )
    repeated = canonical_candidate_id(
        repository_id=101,
        candidate_snapshot_commit_sha="a" * 40,
        repair_commit_sha="c" * 40,
    )

    assert CANDIDATE_ID_PATTERN.fullmatch(first)
    assert first != different_branch
    assert first == repeated


def test_one_commit_fixing_multiple_issues_preserves_all_provenance() -> None:
    candidate_id = canonical_candidate_id(
        repository_id=101,
        candidate_snapshot_commit_sha="a" * 40,
        repair_commit_sha="c" * 40,
    )
    records = [
        source_record_id(
            source_id="fixture-source-003",
            source_revision="d" * 64,
            source_native_identity={"issue_node": node},
        )
        for node in ("issue-a", "issue-b")
    ]

    index = build_candidate_provenance_index(
        [(candidate_id, records[1]), (candidate_id, records[0])]
    )

    assert index == [
        {
            "canonical_candidate_id": candidate_id,
            "source_record_ids": sorted(records),
        }
    ]


def test_backports_and_cherry_picks_remain_distinct() -> None:
    first = _episode(snapshot="a", repair="c")
    backport = _episode(snapshot="b", repair="d")

    assert canonical_candidate_id(
        repository_id=first["github_repository_id"],
        candidate_snapshot_commit_sha=first["candidate_snapshot_commit_sha"],
        repair_commit_sha=first["repair_commit_sha"],
    ) != canonical_candidate_id(
        repository_id=backport["github_repository_id"],
        candidate_snapshot_commit_sha=backport["candidate_snapshot_commit_sha"],
        repair_commit_sha=backport["repair_commit_sha"],
    )
    assert deduplication_decision(first, backport) == "DISTINCT"


def test_equivalent_patch_at_different_shas_is_only_possible_duplicate() -> None:
    patch_sha = "e" * 64
    first = {**_episode(snapshot="a", repair="c"), "patch_sha256": patch_sha}
    second = {**_episode(snapshot="b", repair="d"), "patch_sha256": patch_sha}

    assert deduplication_decision(first, second) == "POSSIBLE_DUPLICATE"


def test_missing_metadata_never_implies_equality() -> None:
    complete = _episode()
    missing = {
        "github_repository_id": None,
        "candidate_snapshot_commit_sha": None,
        "repair_commit_sha": None,
    }

    assert deduplication_decision(complete, missing) == "DISTINCT"


def test_equal_repair_sha_with_different_snapshot_is_possible_duplicate() -> None:
    assert deduplication_decision(
        _episode(snapshot="a", repair="c"),
        _episode(snapshot="b", repair="c"),
    ) == "POSSIBLE_DUPLICATE"


def test_same_pr_with_conflicting_range_is_identity_conflict() -> None:
    first = {**_episode(snapshot="a", repair="c"), "pull_request_number": 7}
    second = {**_episode(snapshot="b", repair="c"), "pull_request_number": 7}

    assert deduplication_decision(first, second) == "IDENTITY_CONFLICT"


def test_created_interval_split_is_disjoint_and_exhaustive() -> None:
    left, right = split_created_interval(
        CreatedInterval(
            path="",
            start_utc="2026-01-01T00:00:00Z",
            end_utc="2026-01-01T00:00:03Z",
        )
    )

    assert left == CreatedInterval(
        "L", "2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z"
    )
    assert right == CreatedInterval(
        "R", "2026-01-01T00:00:02Z", "2026-01-01T00:00:03Z"
    )


def test_partition_query_changes_only_created_qualifier() -> None:
    root = (
        '"fixture phrase" in:title,body is:pr is:merged is:public '
        "created:2020-01-01..2026-08-12"
    )
    interval = CreatedInterval(
        "LR", "2024-01-01T00:00:00Z", "2024-01-31T23:59:59Z"
    )

    assert partition_query(root, interval) == (
        '"fixture phrase" in:title,body is:pr is:merged is:public '
        "created:2024-01-01T00:00:00Z..2024-01-31T23:59:59Z"
    )


def test_over_cap_query_partitions_deterministically_left_first() -> None:
    root = CreatedInterval(
        "", "2026-01-01T00:00:00Z", "2026-01-01T00:00:03Z"
    )
    observations = {
        "": PartitionObservation(1500, False),
        "L": PartitionObservation(700, False),
        "R": PartitionObservation(800, False),
    }

    first = build_created_partition_plan(
        lambda interval: observations[interval.path], root=root
    )
    second = build_created_partition_plan(
        lambda interval: observations[interval.path], root=root
    )

    assert [node.interval.path for node in first] == ["", "L", "R"]
    assert [node.disposition for node in first] == ["SPLIT", "LEAF", "LEAF"]
    assert first == second


def test_partition_count_drift_fails_closed() -> None:
    root = CreatedInterval(
        "", "2026-01-01T00:00:00Z", "2026-01-01T00:00:01Z"
    )
    observations = {
        "": PartitionObservation(1500, False),
        "L": PartitionObservation(700, False),
        "R": PartitionObservation(799, False),
    }

    with pytest.raises(CandidateSourceV03Error) as error:
        build_created_partition_plan(
            lambda interval: observations[interval.path], root=root
        )

    assert _code(error) == "GITHUB_SEARCH_PARTITION_COUNT_MISMATCH"


def test_atomic_overflow_fails_without_semantic_partition() -> None:
    atomic = CreatedInterval(
        "LL", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"
    )

    with pytest.raises(CandidateSourceV03Error) as error:
        build_created_partition_plan(
            lambda _: PartitionObservation(1001, False), root=atomic
        )

    assert _code(error) == "GITHUB_SEARCH_ATOMIC_PARTITION_OVERFLOW"


def test_incomplete_search_partition_fails_closed() -> None:
    with pytest.raises(CandidateSourceV03Error) as error:
        build_created_partition_plan(
            lambda _: PartitionObservation(1, True),
            root=CreatedInterval(
                "", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"
            ),
        )

    assert _code(error) == "GITHUB_SEARCH_INCOMPLETE_RESULTS"


@pytest.mark.parametrize(
    ("attempt", "status", "transport", "action", "delay", "code"),
    [
        (1, 503, None, "RETRY", 2, None),
        (2, None, "READ_TIMEOUT", "RETRY", 4, None),
        (3, 504, None, "FAIL", 0, "API_TRANSIENT_FAILURE_EXHAUSTED"),
        (1, 200, None, "ACCEPT", 0, None),
        (1, 404, None, "FAIL", 0, "API_PERMANENT_HTTP_FAILURE"),
    ],
)
def test_request_retry_policy_is_bounded_and_deterministic(
    attempt: int,
    status: int | None,
    transport: str | None,
    action: str,
    delay: int,
    code: str | None,
) -> None:
    decision = request_decision(
        attempt_number=attempt,
        http_status=status,
        transport_error=transport,
    )

    assert (decision.action, decision.delay_seconds, decision.reason_code) == (
        action,
        delay,
        code,
    )


def test_rate_limit_requires_rate_limit_evidence_for_403() -> None:
    ordinary_forbidden = request_decision(attempt_number=1, http_status=403)
    primary_limit = request_decision(
        attempt_number=1, http_status=403, rate_limit_evidence=True
    )
    too_many = request_decision(attempt_number=1, http_status=429)

    assert ordinary_forbidden.reason_code == "API_PERMANENT_HTTP_FAILURE"
    assert primary_limit.reason_code == "API_RATE_LIMIT_EXHAUSTED"
    assert too_many.reason_code == "API_RATE_LIMIT_EXHAUSTED"
    assert primary_limit.action == too_many.action == "FAIL"


def test_raw_artifact_is_content_addressed_before_normalization() -> None:
    body = b'{"fixture":true}\n'
    descriptor = raw_artifact_descriptor(body, media_type="application/json")

    assert descriptor["path"] == (
        f"raw/sha256/{descriptor['sha256'][:2]}/{descriptor['sha256'][2:]}"
    )
    assert descriptor["size_bytes"] == len(body)
    verify_raw_artifact(body, descriptor)


def test_raw_artifact_tampering_is_rejected() -> None:
    descriptor = raw_artifact_descriptor(b"first", media_type="application/json")

    with pytest.raises(CandidateSourceV03Error) as error:
        verify_raw_artifact(b"second", descriptor)

    assert _code(error) == "RAW_ARTIFACT_HASH_MISMATCH"


def test_multi_commit_ordinary_merge_uses_first_parent_snapshot() -> None:
    episode = resolve_merged_pr_episode(
        repository_id=101,
        merged=True,
        merged_at_utc="2026-01-01T00:00:00Z",
        head_sha="b" * 40,
        repair_endpoint_sha="c" * 40,
        endpoint_parent_shas=["a" * 40, "b" * 40],
        pr_commit_count=4,
    )

    assert episode.candidate_snapshot_commit_sha == "a" * 40
    assert episode.repair_commit_sha == "c" * 40
    assert episode.topology == "ORDINARY_MERGE_COMMIT"


def test_single_commit_single_parent_merge_is_unambiguous() -> None:
    episode = resolve_merged_pr_episode(
        repository_id=101,
        merged=True,
        merged_at_utc="2026-01-01T00:00:00Z",
        head_sha="b" * 40,
        repair_endpoint_sha="c" * 40,
        endpoint_parent_shas=["a" * 40],
        pr_commit_count=1,
    )

    assert episode.candidate_snapshot_commit_sha == "a" * 40
    assert episode.topology == "SINGLE_PARENT_SINGLE_COMMIT"


def test_multi_commit_squash_or_rebase_fails_closed() -> None:
    with pytest.raises(CandidateSourceV03Error) as error:
        resolve_merged_pr_episode(
            repository_id=101,
            merged=True,
            merged_at_utc="2026-01-01T00:00:00Z",
            head_sha="b" * 40,
            repair_endpoint_sha="c" * 40,
            endpoint_parent_shas=["a" * 40],
            pr_commit_count=4,
        )

    assert _code(error) == "GITHUB_PR_MERGE_TOPOLOGY_AMBIGUOUS"


def test_ordinary_merge_head_parent_mismatch_fails_closed() -> None:
    with pytest.raises(CandidateSourceV03Error) as error:
        resolve_merged_pr_episode(
            repository_id=101,
            merged=True,
            merged_at_utc="2026-01-01T00:00:00Z",
            head_sha="b" * 40,
            repair_endpoint_sha="c" * 40,
            endpoint_parent_shas=["a" * 40, "d" * 40],
            pr_commit_count=2,
        )

    assert _code(error) == "GITHUB_PR_ENDPOINT_PARENT_MISMATCH"


def test_deleted_branch_is_irrelevant_when_objects_resolve() -> None:
    episode = resolve_merged_pr_episode(
        repository_id=101,
        merged=True,
        merged_at_utc="2026-01-01T00:00:00Z",
        head_sha="b" * 40,
        repair_endpoint_sha="c" * 40,
        endpoint_parent_shas=["a" * 40, "b" * 40],
        pr_commit_count=2,
    )

    assert episode.topology == "ORDINARY_MERGE_COMMIT"


def test_explicit_advisory_merge_commit_is_ambiguous() -> None:
    with pytest.raises(CandidateSourceV03Error) as error:
        resolve_explicit_commit_episode(
            repository_id=101,
            repair_commit_sha="c" * 40,
            parent_shas=["a" * 40, "b" * 40],
        )

    assert _code(error) == "ADVISORY_COMMIT_PARENT_NOT_SINGLE"


def test_explicit_advisory_single_parent_commit_is_exact() -> None:
    episode = resolve_explicit_commit_episode(
        repository_id=101,
        repair_commit_sha="c" * 40,
        parent_shas=["a" * 40],
    )

    assert episode.candidate_snapshot_commit_sha == "a" * 40
    assert episode.topology == "EXPLICIT_SINGLE_PARENT_COMMIT"


def test_benchmark_metadata_requires_ancestry_proof() -> None:
    with pytest.raises(CandidateSourceV03Error) as error:
        resolve_benchmark_episode(
            repository_id=101,
            buggy_commit_sha="a" * 40,
            fixed_commit_sha="c" * 40,
            buggy_is_ancestor_of_fixed=False,
        )

    assert _code(error) == "BENCHMARK_REPAIR_ANCESTRY_INVALID"


def test_benchmark_metadata_defines_exact_range() -> None:
    episode = resolve_benchmark_episode(
        repository_id=101,
        buggy_commit_sha="a" * 40,
        fixed_commit_sha="c" * 40,
        buggy_is_ancestor_of_fixed=True,
    )

    assert episode.candidate_snapshot_commit_sha == "a" * 40
    assert episode.repair_commit_sha == "c" * 40


def test_capture_schema_records_reproducibility_fields_and_raw_gate() -> None:
    schema = _read(V03 / "raw-capture-manifest.schema.json")
    request = schema["$defs"]["logical_request"]  # type: ignore[index]
    attempt = schema["$defs"]["attempt"]  # type: ignore[index]
    properties = schema["properties"]  # type: ignore[index]

    assert {
        "method",
        "endpoint",
        "api_version",
        "accept",
        "ordered_parameters",
        "sort",
        "order",
        "attempts",
    } <= set(request["required"])
    assert {
        "http_status",
        "response_headers",
        "body",
        "total_count",
        "incomplete_results",
    } <= set(attempt["properties"])
    assert properties["normalization_started"]["const"] is False
    assert properties["credentials_recorded"]["const"] is False
    accounting = properties["source_object_accounting"]
    assert accounting["properties"]["disposition_phase"]["const"] == (
        "NOT_STARTED"
    )
    partition = schema["$defs"]["partition_node"]  # type: ignore[index]
    assert partition["properties"]["incomplete_results"]["type"] == "boolean"


def test_source_record_identity_requires_snapshot_and_multiple_raw_artifacts() -> None:
    schema = _read(V03 / "source-record.schema.json")
    properties = schema["properties"]  # type: ignore[index]
    candidate = schema["$defs"]["candidate_link"]  # type: ignore[index]

    assert properties["source_record_id"]["pattern"] == (
        "^CMVP-SRC-03-[0-9a-f]{64}$"
    )
    assert properties["raw_artifacts"]["minItems"] == 1
    assert "candidate_snapshot_commit_sha" in candidate["required"]
    assert candidate["properties"]["canonical_candidate_id"]["pattern"] == (
        "^CMVP-CAND-03-[0-9a-f]{64}$"
    )


def test_failure_taxonomy_covers_preexecution_cases() -> None:
    amendment = _read(V03 / "amendment.json")
    failures = amendment["failure_semantics"]  # type: ignore[index]
    cases = failures["cases"]
    codes = failures["reason_codes_added"]

    assert {
        "deleted_or_inaccessible_repository",
        "inaccessible_commit",
        "transient_api_failure",
        "malformed_metadata",
        "missing_issue_or_pr",
        "withdrawn_advisory",
        "repository_rename_or_transfer",
        "rate_limit_exhaustion",
        "source_schema_drift",
    } <= set(cases)
    assert {
        "API_RATE_LIMIT_EXHAUSTED",
        "API_TRANSIENT_FAILURE_EXHAUSTED",
        "GITHUB_REPOSITORY_UNAVAILABLE",
        "GITHUB_COMMIT_UNAVAILABLE",
        "GITHUB_ISSUE_OR_PR_UNAVAILABLE",
        "SOURCE_SCHEMA_DRIFT",
    } <= set(codes)


def test_scientific_separation_is_complete_and_has_no_ranking() -> None:
    amendment = _read(V03 / "amendment.json")
    separation = amendment["scientific_separation_override"]  # type: ignore[index]

    assert set(separation["discovery_forbidden_assignments"]) == (
        FORBIDDEN_DISCOVERY_ASSIGNMENTS
    )
    ranking = separation["ranking"].casefold()
    assert "no ml" in ranking
    assert "heuristic" in ranking
    assert "treatment" in ranking


def test_v03_module_has_no_network_or_process_imports() -> None:
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert imported.isdisjoint(
        {"httpx", "requests", "socket", "subprocess", "urllib"}
    )
