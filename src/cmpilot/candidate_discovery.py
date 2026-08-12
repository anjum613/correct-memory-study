"""Reproducible, outcome-blind repository candidate discovery."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


PROTOCOL_VERSION = "benchmark-selection-v0.1"
QUERY_SCHEMA = "candidate-discovery-query-v0.1"
CAPTURE_SCHEMA = "candidate-discovery-capture-v0.1"
SOURCE_LIST_SCHEMA = "candidate-discovery-source-list-v0.1"
MANIFEST_SCHEMA = "candidate-discovery-manifest-v0.1"
INCLUSION_POLICY = "ALL_RETURNED_ITEMS_IN_API_ORDER"
HARD_GATES = (
    "usable_licence",
    "immutable_commit",
    "reproducible_setup",
    "deterministic_baseline_tests",
    "manageable_task_size",
    "no_proprietary_credentials_or_uncontrolled_service",
    "narrow_observable_p_star",
    "one_condition_isolation",
    "target_not_already_vulnerable",
    "faithful_reuse_functional_and_witness_open",
    "secure_reference_functional_and_witness_blocked",
    "implementation_independent_functional_oracle",
    "deterministic_security_witness",
    "independent_approval",
)
RESPONSE_HEADERS = (
    "content-type",
    "date",
    "etag",
    "last-modified",
    "x-github-api-version-selected",
    "x-github-request-id",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "x-ratelimit-resource",
    "x-ratelimit-used",
)


class CandidateDiscoveryError(RuntimeError):
    """Raised when a discovery capture or materialization is invalid."""


@dataclass(frozen=True)
class HttpResponse:
    """Exact response body plus non-sensitive request evidence."""

    status: int
    body: bytes
    headers: Mapping[str, str]


Fetcher = Callable[[str, Mapping[str, str]], HttpResponse]
Clock = Callable[[], str]


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CandidateDiscoveryError(f"cannot read JSON {path}: {error}") from error


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CandidateDiscoveryError(f"{label} must be an object")
    return value


def _require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CandidateDiscoveryError(f"{label} must be a non-empty string")
    return value


def _require_integer(value: Any, label: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise CandidateDiscoveryError(f"{label} must be an integer >= {minimum}")
    return value


def _validate_relative_path(value: Any, label: str) -> Path:
    text = _require_string(value, label)
    path = Path(text)
    if path.is_absolute() or ".." in path.parts:
        raise CandidateDiscoveryError(f"{label} must be a safe relative path")
    return path


def load_query(path: Path) -> Mapping[str, Any]:
    """Load and validate a frozen discovery query."""

    query = _require_mapping(_load_json(path), "query")
    expected = {
        "schema": QUERY_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "inclusion_policy": INCLUSION_POLICY,
    }
    for key, value in expected.items():
        if query.get(key) != value:
            raise CandidateDiscoveryError(f"query {key} must equal {value!r}")
    for key in (
        "source_list_id",
        "forge",
        "endpoint",
        "api_version",
        "accept",
        "user_agent",
        "query",
        "sort",
        "order",
        "discoverer_id",
        "frozen_at_utc",
    ):
        _require_string(query.get(key), f"query.{key}")
    _require_integer(query.get("page"), "query.page")
    _require_integer(query.get("per_page"), "query.per_page")
    _require_integer(query.get("candidate_id_start"), "query.candidate_id_start")
    _validate_relative_path(
        query.get("query_repository_path"), "query.query_repository_path"
    )
    _validate_relative_path(
        query.get("snapshot_repository_path"), "query.snapshot_repository_path"
    )
    pipeline_paths = query.get("pipeline_paths")
    if not isinstance(pipeline_paths, list) or not pipeline_paths:
        raise CandidateDiscoveryError("query.pipeline_paths must be non-empty")
    for index, pipeline_path in enumerate(pipeline_paths, start=1):
        _validate_relative_path(pipeline_path, f"query.pipeline_paths[{index}]")
    return query


def search_url(query: Mapping[str, Any]) -> str:
    """Construct the exact, ordered search request URL."""

    parameters = (
        ("q", str(query["query"])),
        ("sort", str(query["sort"])),
        ("order", str(query["order"])),
        ("per_page", str(query["per_page"])),
        ("page", str(query["page"])),
    )
    return f"{query['endpoint']}?{urlencode(parameters)}"


def _request_headers(query: Mapping[str, Any]) -> dict[str, str]:
    return {
        "Accept": str(query["accept"]),
        "User-Agent": str(query["user_agent"]),
        "X-GitHub-Api-Version": str(query["api_version"]),
    }


def fetch_public_json(url: str, headers: Mapping[str, str]) -> HttpResponse:
    """Fetch one public JSON endpoint without credentials or retries."""

    request = Request(url, headers=dict(headers), method="GET")
    with urlopen(request, timeout=30) as response:  # noqa: S310 - frozen HTTPS URL
        response_headers = {key.casefold(): value for key, value in response.headers.items()}
        return HttpResponse(
            status=response.status,
            body=response.read(),
            headers=response_headers,
        )


def _record_response(
    *,
    root: Path,
    body_path: Path,
    response: HttpResponse,
    url: str,
    kind: str,
    retrieved_at_utc: str,
    position: int | None = None,
    repository_full_name: str | None = None,
) -> dict[str, Any]:
    if response.status != 200:
        raise CandidateDiscoveryError(f"{kind} request returned HTTP {response.status}")
    try:
        json.loads(response.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CandidateDiscoveryError(f"{kind} response is not JSON: {error}") from error
    target = root / body_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(response.body)
    record: dict[str, Any] = {
        "kind": kind,
        "url": url,
        "status": response.status,
        "retrieved_at_utc": retrieved_at_utc,
        "body_path": body_path.as_posix(),
        "body_sha256": _sha256_bytes(response.body),
        "response_headers": {
            key: response.headers[key]
            for key in RESPONSE_HEADERS
            if key in response.headers
        },
    }
    if position is not None:
        record["position"] = position
    if repository_full_name is not None:
        record["repository_full_name"] = repository_full_name
    return record


def capture_snapshot(
    *,
    query_path: Path,
    snapshot_directory: Path,
    fetcher: Fetcher = fetch_public_json,
    clock: Clock = _utc_now,
) -> Mapping[str, Any]:
    """Capture one immutable query page and each returned head commit."""

    query = load_query(query_path)
    if snapshot_directory.exists():
        raise CandidateDiscoveryError(
            f"snapshot directory already exists: {snapshot_directory}"
        )
    snapshot_directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{snapshot_directory.name}.capture-",
        dir=snapshot_directory.parent,
    ) as temporary:
        temporary_root = Path(temporary)
        started_at_utc = clock()
        headers = _request_headers(query)
        exact_search_url = search_url(query)
        search_response = fetcher(exact_search_url, headers)
        requests = [
            _record_response(
                root=temporary_root,
                body_path=Path("raw/search.json"),
                response=search_response,
                url=exact_search_url,
                kind="REPOSITORY_SEARCH",
                retrieved_at_utc=clock(),
            )
        ]
        search_body = _require_mapping(
            json.loads(search_response.body), "repository search response"
        )
        items = search_body.get("items")
        if not isinstance(items, list):
            raise CandidateDiscoveryError("repository search response lacks items")
        if len(items) > int(query["per_page"]):
            raise CandidateDiscoveryError("search returned more than configured per_page")
        if not items:
            raise CandidateDiscoveryError("search returned no candidates")
        for position, raw_item in enumerate(items, start=1):
            item = _require_mapping(raw_item, f"search item {position}")
            full_name = _require_string(item.get("full_name"), "repository full_name")
            default_branch = _require_string(
                item.get("default_branch"), f"{full_name}.default_branch"
            )
            parts = full_name.split("/", maxsplit=1)
            if len(parts) != 2 or not all(parts):
                raise CandidateDiscoveryError(f"invalid repository full_name {full_name!r}")
            owner, repository = parts
            ref_url = (
                "https://api.github.com/repos/"
                f"{quote(owner, safe='')}/{quote(repository, safe='')}/git/ref/heads/"
                f"{quote(default_branch, safe='')}"
            )
            ref_response = fetcher(ref_url, headers)
            requests.append(
                _record_response(
                    root=temporary_root,
                    body_path=Path(f"raw/refs/{position:04d}.json"),
                    response=ref_response,
                    url=ref_url,
                    kind="HEAD_REF",
                    retrieved_at_utc=clock(),
                    position=position,
                    repository_full_name=full_name,
                )
            )
            ref_body = _require_mapping(
                json.loads(ref_response.body), f"head ref {position}"
            )
            ref_object = _require_mapping(
                ref_body.get("object"), f"head ref {position}.object"
            )
            if ref_object.get("type") != "commit":
                raise CandidateDiscoveryError(
                    f"head ref {position} does not resolve to a commit"
                )
            commit_sha = _require_string(
                ref_object.get("sha"), f"head ref {position}.object.sha"
            )
            commit_url = (
                "https://api.github.com/repos/"
                f"{quote(owner, safe='')}/{quote(repository, safe='')}/git/commits/"
                f"{quote(commit_sha, safe='')}"
            )
            commit_response = fetcher(commit_url, headers)
            requests.append(
                _record_response(
                    root=temporary_root,
                    body_path=Path(f"raw/commits/{position:04d}.json"),
                    response=commit_response,
                    url=commit_url,
                    kind="GIT_COMMIT",
                    retrieved_at_utc=clock(),
                    position=position,
                    repository_full_name=full_name,
                )
            )
        manifest = {
            "schema": CAPTURE_SCHEMA,
            "protocol_version": PROTOCOL_VERSION,
            "source_list_id": query["source_list_id"],
            "query_repository_path": query["query_repository_path"],
            "query_sha256": _sha256_file(query_path),
            "started_at_utc": started_at_utc,
            "completed_at_utc": clock(),
            "request_count": len(requests),
            "requests": requests,
            "credentials_used": False,
            "repository_content_fetched": False,
            "treatment_results_consulted": False,
        }
        (temporary_root / "capture-manifest.json").write_bytes(
            _canonical_bytes(manifest)
        )
        Path(temporary).rename(snapshot_directory)
    return manifest


def _load_verified_capture(
    *, query_path: Path, snapshot_directory: Path
) -> tuple[Mapping[str, Any], Mapping[str, Any], list[Mapping[str, Any]]]:
    query = load_query(query_path)
    manifest = _require_mapping(
        _load_json(snapshot_directory / "capture-manifest.json"), "capture manifest"
    )
    expected = {
        "schema": CAPTURE_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "source_list_id": query["source_list_id"],
        "query_sha256": _sha256_file(query_path),
        "credentials_used": False,
        "repository_content_fetched": False,
        "treatment_results_consulted": False,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise CandidateDiscoveryError(
                f"capture manifest {key} does not match the frozen query"
            )
    raw_requests = manifest.get("requests")
    if not isinstance(raw_requests, list) or not raw_requests:
        raise CandidateDiscoveryError("capture manifest has no requests")
    requests: list[Mapping[str, Any]] = []
    for index, raw_request in enumerate(raw_requests, start=1):
        request = _require_mapping(raw_request, f"capture request {index}")
        body_path = _validate_relative_path(
            request.get("body_path"), f"capture request {index} body_path"
        )
        body = (snapshot_directory / body_path).read_bytes()
        if _sha256_bytes(body) != request.get("body_sha256"):
            raise CandidateDiscoveryError(f"raw response hash mismatch: {body_path}")
        if request.get("status") != 200:
            raise CandidateDiscoveryError(f"capture request {index} was not HTTP 200")
        requests.append(request)
    if manifest.get("request_count") != len(requests):
        raise CandidateDiscoveryError("capture request_count mismatch")
    return query, manifest, requests


def _source_from_item(
    *,
    item: Mapping[str, Any],
    commit: Mapping[str, Any],
    query: Mapping[str, Any],
    manifest: Mapping[str, Any],
    source_list_sha256: str | None,
    position: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    full_name = _require_string(item.get("full_name"), f"item {position}.full_name")
    parts = full_name.split("/", maxsplit=1)
    if len(parts) != 2 or not all(parts):
        raise CandidateDiscoveryError(f"invalid repository full_name {full_name!r}")
    owner, name = parts
    commit_sha = _require_string(commit.get("sha"), f"{full_name}.commit.sha")
    committer = _require_mapping(
        commit.get("committer"), f"{full_name}.commit.committer"
    )
    tree = _require_mapping(commit.get("tree"), f"{full_name}.commit.tree")
    tree_sha = _require_string(tree.get("sha"), f"{full_name}.tree.sha")
    tree_url = _require_string(tree.get("url"), f"{full_name}.tree.url")
    license_value = item.get("license")
    licence_spdx = "NOASSERTION"
    if isinstance(license_value, Mapping):
        spdx = license_value.get("spdx_id")
        if isinstance(spdx, str) and spdx.strip():
            licence_spdx = spdx
    metadata = {
        "repository": {
            "id": item.get("id"),
            "node_id": item.get("node_id"),
            "full_name": full_name,
            "html_url": item.get("html_url"),
            "default_branch": item.get("default_branch"),
            "license_spdx": licence_spdx,
            "language": item.get("language"),
            "size_kib": item.get("size"),
            "stargazers_count": item.get("stargazers_count"),
            "archived": item.get("archived"),
            "fork": item.get("fork"),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "pushed_at": item.get("pushed_at"),
        },
        "commit": {
            "sha": commit_sha,
            "html_url": commit.get("html_url"),
            "committer_date": committer.get("date"),
            "tree_sha": tree_sha,
            "tree_url": tree_url,
            "verification": {
                "verified": _require_mapping(
                    commit.get("verification"), f"{full_name}.commit.verification"
                ).get("verified"),
                "reason": _require_mapping(
                    commit.get("verification"), f"{full_name}.commit.verification"
                ).get("reason"),
                "verified_at": _require_mapping(
                    commit.get("verification"), f"{full_name}.commit.verification"
                ).get("verified_at"),
            },
        },
    }
    tree_identity = {
        "forge": query["forge"],
        "repository_full_name": full_name,
        "commit_sha": commit_sha,
        "git_tree_sha": tree_sha,
        "git_tree_url": tree_url,
    }
    source = {
        "forge": query["forge"],
        "repository_url": _require_string(
            item.get("html_url"), f"{full_name}.html_url"
        ),
        "upstream_owner": owner,
        "upstream_name": name,
        "licence_spdx": licence_spdx,
        "discovery": {
            "source_list_id": query["source_list_id"],
            "source_list_sha256": source_list_sha256,
            "position": position,
            "discovered_at_utc": manifest["started_at_utc"],
            "discoverer_id": query["discoverer_id"],
        },
        "snapshot": {
            "commit_sha": commit_sha,
            "commit_date_utc": _require_string(
                committer.get("date"), f"{full_name}.commit.committer.date"
            ),
            "tree_sha256": _sha256_bytes(_canonical_bytes(tree_identity)),
            "metadata_sha256": _sha256_bytes(_canonical_bytes(metadata)),
            "retrieval_method": (
                "GitHub REST API 2022-11-28 repository-search, head-reference, "
                "and Git commit-object metadata capture; no clone, archive, "
                "repository file content, install, or execution"
            ),
        },
    }
    return source, metadata


def build_source_list(
    *, query_path: Path, snapshot_directory: Path
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Build deterministic source-list and raw ledger records in memory."""

    query, manifest, requests = _load_verified_capture(
        query_path=query_path, snapshot_directory=snapshot_directory
    )
    search_requests = [item for item in requests if item.get("kind") == "REPOSITORY_SEARCH"]
    if len(search_requests) != 1:
        raise CandidateDiscoveryError("capture must contain exactly one search request")
    search_request = search_requests[0]
    search_body = _require_mapping(
        _load_json(snapshot_directory / str(search_request["body_path"])),
        "search body",
    )
    items = search_body.get("items")
    if not isinstance(items, list) or not items:
        raise CandidateDiscoveryError("search body has no items")
    ref_requests = {
        request.get("position"): request
        for request in requests
        if request.get("kind") == "HEAD_REF"
    }
    commit_requests = {
        request.get("position"): request
        for request in requests
        if request.get("kind") == "GIT_COMMIT"
    }
    expected_positions = set(range(1, len(items) + 1))
    if set(ref_requests) != expected_positions:
        raise CandidateDiscoveryError("head-ref captures do not cover every position")
    if set(commit_requests) != expected_positions:
        raise CandidateDiscoveryError("Git commit captures do not cover every position")
    candidate_start = int(query["candidate_id_start"])
    candidates: list[dict[str, Any]] = []
    provisional_sources: list[dict[str, Any]] = []
    for position, raw_item in enumerate(items, start=1):
        item = _require_mapping(raw_item, f"search item {position}")
        ref_request = ref_requests[position]
        commit_request = commit_requests[position]
        full_name = _require_string(item.get("full_name"), f"item {position}.full_name")
        if ref_request.get("repository_full_name") != full_name:
            raise CandidateDiscoveryError(f"head-ref capture mismatch at position {position}")
        if commit_request.get("repository_full_name") != full_name:
            raise CandidateDiscoveryError(f"commit capture mismatch at position {position}")
        ref_body = _require_mapping(
            _load_json(snapshot_directory / str(ref_request["body_path"])),
            f"head-ref body {position}",
        )
        ref_object = _require_mapping(
            ref_body.get("object"), f"head-ref body {position}.object"
        )
        commit = _require_mapping(
            _load_json(snapshot_directory / str(commit_request["body_path"])),
            f"commit body {position}",
        )
        if ref_object.get("type") != "commit" or ref_object.get("sha") != commit.get("sha"):
            raise CandidateDiscoveryError(
                f"head-ref and Git commit mismatch at position {position}"
            )
        source, metadata = _source_from_item(
            item=item,
            commit=commit,
            query=query,
            manifest=manifest,
            source_list_sha256=None,
            position=position,
        )
        candidate_id = f"CMVP-CAND-{candidate_start + position - 1:04d}"
        candidates.append(
            {
                "candidate_id": candidate_id,
                "position": position,
                "source": source,
                "normalized_metadata": metadata,
                "raw_evidence": [
                    {
                        "path": search_request["body_path"],
                        "sha256": search_request["body_sha256"],
                    },
                    {
                        "path": ref_request["body_path"],
                        "sha256": ref_request["body_sha256"],
                    },
                    {
                        "path": commit_request["body_path"],
                        "sha256": commit_request["body_sha256"],
                    },
                ],
            }
        )
        provisional_sources.append(source)
    source_list = {
        "schema": SOURCE_LIST_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "source_list_id": query["source_list_id"],
        "inclusion_policy": INCLUSION_POLICY,
        "query": {
            "path": query["query_repository_path"],
            "sha256": _sha256_file(query_path),
        },
        "capture": {
            "manifest": {
                "path": (
                    f"{query['snapshot_repository_path']}/capture-manifest.json"
                ),
                "sha256": _sha256_file(snapshot_directory / "capture-manifest.json"),
            },
            "started_at_utc": manifest["started_at_utc"],
            "completed_at_utc": manifest["completed_at_utc"],
        },
        "candidate_count": len(candidates),
        "candidates": candidates,
        "screening_status": "NOT_STARTED",
        "treatment_results_consulted": False,
    }
    source_list_sha256 = _sha256_bytes(_canonical_bytes(source_list))
    ledger_records: list[dict[str, Any]] = []
    source_list_evidence = {
        "path": f"{query['snapshot_repository_path']}/source-list.json",
        "sha256": source_list_sha256,
    }
    for candidate, provisional_source in zip(candidates, provisional_sources):
        source = json.loads(json.dumps(provisional_source))
        source["discovery"]["source_list_sha256"] = source_list_sha256
        ledger_records.append(
            {
                "candidate_id": candidate["candidate_id"],
                "protocol_version": PROTOCOL_VERSION,
                "current_state": "DISCOVERED",
                "status_history": [
                    {
                        "sequence": 1,
                        "state": "DISCOVERED",
                        "recorded_at_utc": manifest["started_at_utc"],
                        "actor_id": query["discoverer_id"],
                        "protocol_version": PROTOCOL_VERSION,
                        "rationale": (
                            "Imported without screening from frozen source-list "
                            f"position {candidate['position']}"
                        ),
                        "evidence": [source_list_evidence],
                    }
                ],
                "source": source,
                "trust_family": None,
                "mechanism_key": None,
                "hard_gates": {
                    gate: {"status": "NOT_ASSESSED", "evidence": []}
                    for gate in HARD_GATES
                },
                "treatment_results_consulted": False,
            }
        )
    return source_list, ledger_records


def _project_artifacts(
    *,
    project_root: Path,
    query: Mapping[str, Any],
    snapshot_directory: Path,
    source_list_bytes: bytes,
) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    for raw_path in sorted((snapshot_directory / "raw").rglob("*.json")):
        relative = raw_path.relative_to(snapshot_directory).as_posix()
        artifacts.append({"path": relative, "sha256": _sha256_file(raw_path)})
    artifacts.extend(
        [
            {
                "path": "capture-manifest.json",
                "sha256": _sha256_file(snapshot_directory / "capture-manifest.json"),
            },
            {"path": "source-list.json", "sha256": _sha256_bytes(source_list_bytes)},
        ]
    )
    for configured_path in query["pipeline_paths"]:
        path = project_root / str(configured_path)
        if not path.is_file():
            raise CandidateDiscoveryError(f"pipeline artifact is missing: {path}")
        artifacts.append(
            {"path": str(configured_path), "sha256": _sha256_file(path)}
        )
    query_path = project_root / str(query["query_repository_path"])
    artifacts.append(
        {"path": str(query["query_repository_path"]), "sha256": _sha256_file(query_path)}
    )
    return sorted(artifacts, key=lambda item: item["path"])


def _ledger_bytes(records: Sequence[Mapping[str, Any]]) -> bytes:
    return b"".join(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
        + b"\n"
        for record in records
    )


def materialize_snapshot(
    *,
    project_root: Path,
    query_path: Path,
    snapshot_directory: Path,
    ledger_path: Path,
) -> Mapping[str, Any]:
    """Materialize immutable discovery artifacts and append raw records."""

    query = load_query(query_path)
    expected_snapshot = project_root / str(query["snapshot_repository_path"])
    if snapshot_directory.resolve() != expected_snapshot.resolve():
        raise CandidateDiscoveryError("snapshot path differs from frozen query")
    source_list_path = snapshot_directory / "source-list.json"
    discovery_manifest_path = snapshot_directory / "discovery-manifest.json"
    if source_list_path.exists() or discovery_manifest_path.exists():
        raise CandidateDiscoveryError("materialized discovery artifacts already exist")
    source_list, records = build_source_list(
        query_path=query_path, snapshot_directory=snapshot_directory
    )
    source_list_bytes = _canonical_bytes(source_list)
    existing_lines = [
        line for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    existing_ids: set[str] = set()
    for line in existing_lines:
        record = _require_mapping(json.loads(line), "existing ledger record")
        candidate_id = _require_string(record.get("candidate_id"), "candidate_id")
        existing_ids.add(candidate_id)
    new_ids = {str(record["candidate_id"]) for record in records}
    conflicts = sorted(existing_ids & new_ids)
    if conflicts:
        raise CandidateDiscoveryError(f"candidate IDs already exist: {conflicts}")
    artifacts = _project_artifacts(
        project_root=project_root,
        query=query,
        snapshot_directory=snapshot_directory,
        source_list_bytes=source_list_bytes,
    )
    discovery_manifest = {
        "schema": MANIFEST_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "source_list_id": query["source_list_id"],
        "generated_at_utc": source_list["capture"]["completed_at_utc"],
        "self_excluding": True,
        "artifacts": artifacts,
        "candidate_ids": [record["candidate_id"] for record in records],
        "candidate_count": len(records),
        "inclusion_policy": INCLUSION_POLICY,
        "screening_status": "NOT_STARTED",
        "treatment_results_consulted": False,
    }
    source_list_path.write_bytes(source_list_bytes)
    discovery_manifest_path.write_bytes(_canonical_bytes(discovery_manifest))
    with ledger_path.open("ab") as ledger:
        ledger.write(_ledger_bytes(records))
    return discovery_manifest


def verify_snapshot(
    *,
    project_root: Path,
    query_path: Path,
    snapshot_directory: Path,
    ledger_path: Path,
) -> dict[str, Any]:
    """Verify capture hashes, normalized bytes, manifest, and ledger links."""

    query = load_query(query_path)
    expected_source_list, expected_records = build_source_list(
        query_path=query_path, snapshot_directory=snapshot_directory
    )
    expected_source_bytes = _canonical_bytes(expected_source_list)
    source_list_path = snapshot_directory / "source-list.json"
    if source_list_path.read_bytes() != expected_source_bytes:
        raise CandidateDiscoveryError("source-list bytes are not reproducible")
    expected_artifacts = _project_artifacts(
        project_root=project_root,
        query=query,
        snapshot_directory=snapshot_directory,
        source_list_bytes=expected_source_bytes,
    )
    manifest = _require_mapping(
        _load_json(snapshot_directory / "discovery-manifest.json"),
        "discovery manifest",
    )
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise CandidateDiscoveryError("wrong discovery manifest schema")
    if manifest.get("artifacts") != expected_artifacts:
        raise CandidateDiscoveryError("discovery manifest artifact inventory mismatch")
    if manifest.get("candidate_ids") != [
        record["candidate_id"] for record in expected_records
    ]:
        raise CandidateDiscoveryError("discovery manifest candidate order mismatch")
    ledger_records: dict[str, Mapping[str, Any]] = {}
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = _require_mapping(json.loads(line), "ledger record")
        candidate_id = _require_string(record.get("candidate_id"), "candidate_id")
        if candidate_id in ledger_records:
            raise CandidateDiscoveryError(f"duplicate ledger candidate {candidate_id}")
        ledger_records[candidate_id] = record
    for expected in expected_records:
        candidate_id = str(expected["candidate_id"])
        actual = ledger_records.get(candidate_id)
        if actual is None:
            raise CandidateDiscoveryError(f"missing ledger candidate {candidate_id}")
        for key in ("protocol_version", "source", "trust_family", "mechanism_key"):
            if actual.get(key) != expected.get(key):
                raise CandidateDiscoveryError(
                    f"ledger {candidate_id} differs from discovery source at {key}"
                )
        history = actual.get("status_history")
        if not isinstance(history, list) or not history or history[0] != expected["status_history"][0]:
            raise CandidateDiscoveryError(
                f"ledger {candidate_id} lacks the frozen initial history event"
            )
        if actual.get("treatment_results_consulted") is not False:
            raise CandidateDiscoveryError(
                f"ledger {candidate_id} lacks outcome-blind certification"
            )
    return {
        "schema": "candidate-discovery-verification-v0.1",
        "pass": True,
        "source_list_id": query["source_list_id"],
        "candidate_count": len(expected_records),
        "candidate_ids": [record["candidate_id"] for record in expected_records],
        "source_list_sha256": _sha256_bytes(expected_source_bytes),
        "discovery_manifest_sha256": _sha256_file(
            snapshot_directory / "discovery-manifest.json"
        ),
        "network_accessed": False,
        "treatment_results_consulted": False,
    }
