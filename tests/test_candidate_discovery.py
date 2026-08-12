from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
import subprocess
import sys

import pytest

from cmpilot.candidate_discovery import (
    CandidateDiscoveryError,
    HttpResponse,
    build_source_list,
    capture_snapshot,
    load_query,
    materialize_snapshot,
    search_url,
    verify_snapshot,
)


ROOT = Path(__file__).parents[1]
FROZEN_QUERY = ROOT / "benchmark-selection/discovery/v0.1/query.json"
SOURCE_SCHEMA = (
    ROOT / "benchmark-selection/discovery/v0.1/source-list.schema.json"
)
DISCOVERY_SCRIPT = ROOT / "scripts/discover_candidates.py"


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _query() -> dict[str, object]:
    return {
        "accept": "application/vnd.github+json",
        "api_version": "2022-11-28",
        "candidate_id_start": 1,
        "discoverer_id": "test-discovery",
        "endpoint": "https://api.github.com/search/repositories",
        "forge": "github.com",
        "frozen_at_utc": "2026-08-12T00:00:00Z",
        "inclusion_policy": "ALL_RETURNED_ITEMS_IN_API_ORDER",
        "order": "desc",
        "page": 1,
        "per_page": 2,
        "pipeline_paths": [
            "pipeline/core.py",
            "pipeline/cli.py",
            "pipeline/source-list.schema.json",
        ],
        "protocol_version": "benchmark-selection-v0.1",
        "query": "language:Python fork:false",
        "query_repository_path": "query.json",
        "schema": "candidate-discovery-query-v0.1",
        "snapshot_repository_path": "snapshot",
        "sort": "stars",
        "source_list_id": "fixture-source-001",
        "user_agent": "candidate-discovery-test/0.1",
    }


def _repository(
    *, repository_id: int, full_name: str, default_branch: str
) -> dict[str, object]:
    return {
        "id": repository_id,
        "node_id": f"repo-node-{repository_id}",
        "full_name": full_name,
        "html_url": f"https://github.com/{full_name}",
        "default_branch": default_branch,
        "license": {"spdx_id": "MIT"},
        "language": "Python",
        "size": 1000 + repository_id,
        "stargazers_count": 200 - repository_id,
        "archived": False,
        "fork": False,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2026-08-01T00:00:00Z",
        "pushed_at": "2026-08-01T00:00:00Z",
    }


def _commit(*, full_name: str, sha_character: str) -> dict[str, object]:
    commit_sha = sha_character * 40
    tree_sha = chr(ord(sha_character) + 1) * 40
    return {
        "sha": commit_sha,
        "html_url": f"https://github.com/{full_name}/commit/{commit_sha}",
        "committer": {"date": "2026-08-01T00:00:00Z"},
        "tree": {
            "sha": tree_sha,
            "url": f"https://api.github.com/repos/{full_name}/git/trees/{tree_sha}",
        },
        "verification": {
            "verified": True,
            "reason": "valid",
            "verified_at": "2026-08-01T00:00:00Z",
        },
    }


def _fixture_capture(tmp_path: Path) -> tuple[Path, Path, Path]:
    query_path = tmp_path / "query.json"
    query_value = _query()
    _write_json(query_path, query_value)
    for pipeline_path in query_value["pipeline_paths"]:  # type: ignore[union-attr]
        target = tmp_path / str(pipeline_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fixture\n", encoding="utf-8")

    repositories = [
        _repository(repository_id=1, full_name="alpha/one", default_branch="main"),
        _repository(
            repository_id=2,
            full_name="beta/two",
            default_branch="release/v1",
        ),
    ]
    bodies = {
        search_url(query_value): {"total_count": 2, "items": repositories},
        "https://api.github.com/repos/alpha/one/git/ref/heads/main": {
            "ref": "refs/heads/main",
            "object": {"type": "commit", "sha": "a" * 40},
        },
        f"https://api.github.com/repos/alpha/one/git/commits/{'a' * 40}": _commit(
            full_name="alpha/one", sha_character="a"
        ),
        "https://api.github.com/repos/beta/two/git/ref/heads/release%2Fv1": {
            "ref": "refs/heads/release/v1",
            "object": {"type": "commit", "sha": "c" * 40},
        },
        f"https://api.github.com/repos/beta/two/git/commits/{'c' * 40}": _commit(
            full_name="beta/two", sha_character="c"
        ),
    }
    requested: list[str] = []

    def fetcher(url: str, headers: Mapping[str, str]) -> HttpResponse:
        requested.append(url)
        assert "Authorization" not in headers
        assert headers["X-GitHub-Api-Version"] == "2022-11-28"
        return HttpResponse(
            status=200,
            body=json.dumps(bodies[url], separators=(",", ":")).encode("utf-8"),
            headers={
                "content-type": "application/json; charset=utf-8",
                "x-github-request-id": f"fixture-{len(requested)}",
            },
        )

    timestamps = iter(
        [
            "2026-08-12T00:00:00Z",
            "2026-08-12T00:00:01Z",
            "2026-08-12T00:00:02Z",
            "2026-08-12T00:00:03Z",
            "2026-08-12T00:00:04Z",
            "2026-08-12T00:00:05Z",
            "2026-08-12T00:00:06Z",
        ]
    )
    snapshot = tmp_path / "snapshot"
    capture_snapshot(
        query_path=query_path,
        snapshot_directory=snapshot,
        fetcher=fetcher,
        clock=lambda: next(timestamps),
    )
    assert requested == list(bodies)
    ledger = tmp_path / "candidate-ledger.jsonl"
    ledger.write_text("", encoding="utf-8")
    return query_path, snapshot, ledger


def test_frozen_query_precommits_source_order_and_small_batch() -> None:
    query = load_query(FROZEN_QUERY)

    assert query["inclusion_policy"] == "ALL_RETURNED_ITEMS_IN_API_ORDER"
    assert query["per_page"] == 8
    assert query["page"] == 1
    assert query["candidate_id_start"] == 1
    assert "treatment" not in str(query["query"]).casefold()


def test_source_list_schema_is_json_schema_2020_12() -> None:
    schema = json.loads(SOURCE_SCHEMA.read_text(encoding="utf-8"))

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["properties"]["screening_status"]["const"] == "NOT_STARTED"
    assert schema["properties"]["treatment_results_consulted"]["const"] is False


def test_discovery_cli_loads_checked_out_source_tree() -> None:
    result = subprocess.run(
        [sys.executable, str(DISCOVERY_SCRIPT), "--help"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_capture_is_metadata_only_complete_and_credential_free(tmp_path: Path) -> None:
    _, snapshot, _ = _fixture_capture(tmp_path)
    manifest = json.loads(
        (snapshot / "capture-manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["request_count"] == 5
    assert manifest["credentials_used"] is False
    assert manifest["repository_content_fetched"] is False
    assert [request["kind"] for request in manifest["requests"]] == [
        "REPOSITORY_SEARCH",
        "HEAD_REF",
        "GIT_COMMIT",
        "HEAD_REF",
        "GIT_COMMIT",
    ]


def test_materialization_imports_every_item_in_source_order(tmp_path: Path) -> None:
    query_path, snapshot, ledger = _fixture_capture(tmp_path)

    manifest = materialize_snapshot(
        project_root=tmp_path,
        query_path=query_path,
        snapshot_directory=snapshot,
        ledger_path=ledger,
    )
    records = [json.loads(line) for line in ledger.read_text().splitlines()]

    assert manifest["candidate_ids"] == ["CMVP-CAND-0001", "CMVP-CAND-0002"]
    assert [record["source"]["upstream_name"] for record in records] == [
        "one",
        "two",
    ]
    assert all(record["current_state"] == "DISCOVERED" for record in records)
    assert all(record["trust_family"] is None for record in records)
    assert all(record["mechanism_key"] is None for record in records)
    assert all(
        set(gate["status"] for gate in record["hard_gates"].values())
        == {"NOT_ASSESSED"}
        for record in records
    )


def test_offline_build_and_verification_are_deterministic(tmp_path: Path) -> None:
    query_path, snapshot, ledger = _fixture_capture(tmp_path)
    first_source, first_records = build_source_list(
        query_path=query_path, snapshot_directory=snapshot
    )
    second_source, second_records = build_source_list(
        query_path=query_path, snapshot_directory=snapshot
    )
    materialize_snapshot(
        project_root=tmp_path,
        query_path=query_path,
        snapshot_directory=snapshot,
        ledger_path=ledger,
    )

    verification = verify_snapshot(
        project_root=tmp_path,
        query_path=query_path,
        snapshot_directory=snapshot,
        ledger_path=ledger,
    )

    assert first_source == second_source
    assert first_records == second_records
    assert verification["pass"] is True
    assert verification["network_accessed"] is False
    assert verification["candidate_count"] == 2


def test_raw_response_tampering_is_detected(tmp_path: Path) -> None:
    query_path, snapshot, _ = _fixture_capture(tmp_path)
    (snapshot / "raw/commits/0001.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(CandidateDiscoveryError, match="raw response hash mismatch"):
        build_source_list(query_path=query_path, snapshot_directory=snapshot)


def test_capture_and_materialization_refuse_overwrite(tmp_path: Path) -> None:
    query_path, snapshot, ledger = _fixture_capture(tmp_path)

    with pytest.raises(CandidateDiscoveryError, match="already exists"):
        capture_snapshot(query_path=query_path, snapshot_directory=snapshot)

    materialize_snapshot(
        project_root=tmp_path,
        query_path=query_path,
        snapshot_directory=snapshot,
        ledger_path=ledger,
    )
    with pytest.raises(CandidateDiscoveryError, match="already exist"):
        materialize_snapshot(
            project_root=tmp_path,
            query_path=query_path,
            snapshot_directory=snapshot,
            ledger_path=ledger,
        )
