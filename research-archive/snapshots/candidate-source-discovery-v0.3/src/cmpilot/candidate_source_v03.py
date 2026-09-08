"""Pure, offline invariants for candidate-source protocol v0.3.

The module validates prospective specifications and synthetic metadata only.
It intentionally contains no HTTP, git, subprocess, model, or experiment
access path.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any


PROTOCOL_VERSION = "benchmark-selection-source-v0.3"
CANDIDATE_ID_PATTERN = re.compile(r"^CMVP-CAND-03-[0-9a-f]{64}$")
SOURCE_RECORD_ID_PATTERN = re.compile(r"^CMVP-SRC-03-[0-9a-f]{64}$")
SHA1_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CREATED_QUALIFIER_PATTERN = re.compile(r"(?<!\S)created:[^\s]+")
TRANSIENT_HTTP_STATUSES = frozenset({500, 502, 503, 504})
TRANSIENT_TRANSPORT_ERRORS = frozenset(
    {"CONNECT_TIMEOUT", "READ_TIMEOUT", "CONNECTION_RESET"}
)
RETRY_DELAYS_SECONDS = (2, 4)
MAXIMUM_ATTEMPTS = 3
SEARCH_RESULT_CAP = 1000
ROOT_START_UTC = "2020-01-01T00:00:00Z"
ROOT_END_UTC = "2026-08-12T23:59:59Z"
FORBIDDEN_DISCOVERY_ASSIGNMENTS = frozenset(
    {
        "benchmark_inclusion",
        "experimental_status",
        "model_feasibility",
        "p_star",
        "security_relevance_score",
        "triplet_feasibility",
        "trust_family",
    }
)
V02_HASHES = {
    "README.md": "532359e15bc814c0edf805401237fbb5551a7973e469a73c5b8c2083044f2fd3",
    "protocol.json": "8231a516f751953acb14593a157ecde8428cc012c38f5c8871c3fe1d12b60817",
    "repository-repair-tasks.json": (
        "7f251c7b89e7a61cbbfe248ff4843efd7c862eeb5f0e26e82376315a3b505979"
    ),
    "security-advisory-repairs.json": (
        "fe3c1b62d04dc2687ce619d814667e2daf04525eb80ab1a0f857c71fbe44b32a"
    ),
    "source-priority-deduplication.json": (
        "50c11a82eeb59ba8b1c2b0e7c371f16a6bf277179c5aa761225a3a10848d268e"
    ),
    "source-record.schema.json": (
        "1f84985072bc7e090381fb8fe2b2a2885f0442033436cad898d7a7427557d58c"
    ),
    "source-rejection-codes.json": (
        "de492d323e6a475aec34a7d88687384da663e0ae4090b6dc4ada14db1f10b92a"
    ),
    "trust-boundary-issues-prs.json": (
        "7ccf92717a470b5a1f234054d9231516f8b16c55908ac678d89886ec5528b388"
    ),
}


class CandidateSourceV03Error(ValueError):
    """An offline v0.3 invariant failed with a stable reason code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CreatedInterval:
    """One inclusive UTC-second search partition."""

    path: str
    start_utc: str
    end_utc: str


@dataclass(frozen=True)
class PartitionObservation:
    """Synthetic or captured count evidence for one partition node."""

    total_count: int
    incomplete_results: bool


@dataclass(frozen=True)
class PartitionNode:
    """One deterministic node in a depth-first partition plan."""

    interval: CreatedInterval
    total_count: int
    disposition: str


@dataclass(frozen=True)
class RepairEpisode:
    """An exact repository state transition used for candidate identity."""

    canonical_candidate_id: str
    github_repository_id: int
    candidate_snapshot_commit_sha: str
    repair_commit_sha: str
    topology: str


@dataclass(frozen=True)
class RequestDecision:
    """Deterministic action after one request attempt."""

    action: str
    delay_seconds: int
    reason_code: str | None


CountProvider = Callable[[CreatedInterval], PartitionObservation]


def canonical_json_bytes(value: Any) -> bytes:
    """Encode the canonical JSON representation used by v0.3 IDs."""

    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise CandidateSourceV03Error(
            "NON_CANONICAL_IDENTITY_INPUT", str(error)
        ) from error


def _digest_identifier(prefix: str, value: Mapping[str, Any]) -> str:
    return prefix + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _require_repository_id(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CandidateSourceV03Error(
            "GITHUB_REPOSITORY_ID_MISSING",
            "a positive GitHub repository numeric ID is required",
        )
    return value


def _require_sha(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or SHA1_PATTERN.fullmatch(value) is None:
        raise CandidateSourceV03Error(
            "REPAIR_IDENTITY_INCOMPLETE",
            f"{label} must be a lowercase 40-hex SHA",
        )
    return value


def canonical_candidate_id(
    *,
    repository_id: Any,
    candidate_snapshot_commit_sha: Any,
    repair_commit_sha: Any,
) -> str:
    """Identify one exact repository, snapshot, and repair endpoint range."""

    envelope = {
        "candidate_snapshot_commit_sha": _require_sha(
            candidate_snapshot_commit_sha,
            label="candidate_snapshot_commit_sha",
        ),
        "github_repository_id": _require_repository_id(repository_id),
        "protocol_version": PROTOCOL_VERSION,
        "repair_commit_sha": _require_sha(
            repair_commit_sha, label="repair_commit_sha"
        ),
    }
    return _digest_identifier("CMVP-CAND-03-", envelope)


def source_record_id(
    *, source_id: str, source_revision: str, source_native_identity: Mapping[str, Any]
) -> str:
    """Identify one object in an immutable source without a record ceiling."""

    if (
        not isinstance(source_id, str)
        or not source_id
        or not isinstance(source_revision, str)
        or not (
            SHA1_PATTERN.fullmatch(source_revision)
            or SHA256_PATTERN.fullmatch(source_revision)
        )
        or not source_native_identity
    ):
        raise CandidateSourceV03Error(
            "SOURCE_IDENTITY_FIELD_MISSING",
            "source ID, immutable revision, and native identity are required",
        )
    return _digest_identifier(
        "CMVP-SRC-03-",
        {
            "protocol_version": PROTOCOL_VERSION,
            "source_id": source_id,
            "source_native_identity": source_native_identity,
            "source_revision": source_revision,
        },
    )


def _parse_utc_second(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise CandidateSourceV03Error(
            "PARTITION_TIMESTAMP_INVALID", "timestamp must end in Z"
        )
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError as error:
        raise CandidateSourceV03Error(
            "PARTITION_TIMESTAMP_INVALID", str(error)
        ) from error
    return parsed


def _format_utc_second(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def split_created_interval(
    interval: CreatedInterval,
) -> tuple[CreatedInterval, CreatedInterval]:
    """Bisect an inclusive UTC-second interval without overlap or gaps."""

    start = _parse_utc_second(interval.start_utc)
    end = _parse_utc_second(interval.end_utc)
    if start >= end:
        raise CandidateSourceV03Error(
            "GITHUB_SEARCH_ATOMIC_PARTITION_OVERFLOW",
            "an atomic interval cannot be split further",
        )
    midpoint = start + timedelta(seconds=int((end - start).total_seconds()) // 2)
    return (
        CreatedInterval(
            path=interval.path + "L",
            start_utc=_format_utc_second(start),
            end_utc=_format_utc_second(midpoint),
        ),
        CreatedInterval(
            path=interval.path + "R",
            start_utc=_format_utc_second(midpoint + timedelta(seconds=1)),
            end_utc=_format_utc_second(end),
        ),
    )


def partition_query(root_query: str, interval: CreatedInterval) -> str:
    """Replace exactly one created qualifier and no other query token."""

    matches = list(CREATED_QUALIFIER_PATTERN.finditer(root_query))
    if len(matches) != 1:
        raise CandidateSourceV03Error(
            "GITHUB_QUERY_CREATED_QUALIFIER_INVALID",
            "root query must contain exactly one created qualifier",
        )
    replacement = f"created:{interval.start_utc}..{interval.end_utc}"
    return CREATED_QUALIFIER_PATTERN.sub(replacement, root_query, count=1)


def build_created_partition_plan(
    count_provider: CountProvider,
    *,
    root: CreatedInterval | None = None,
) -> tuple[PartitionNode, ...]:
    """Build a deterministic left-first partition tree from count evidence."""

    root_interval = root or CreatedInterval("", ROOT_START_UTC, ROOT_END_UTC)
    nodes: list[PartitionNode] = []

    def visit(interval: CreatedInterval) -> int:
        observation = count_provider(interval)
        if (
            isinstance(observation.total_count, bool)
            or not isinstance(observation.total_count, int)
            or observation.total_count < 0
        ):
            raise CandidateSourceV03Error(
                "SOURCE_SCHEMA_DRIFT", "total_count must be non-negative integer"
            )
        if observation.incomplete_results:
            raise CandidateSourceV03Error(
                "GITHUB_SEARCH_INCOMPLETE_RESULTS",
                "incomplete_results=true fails the source transaction",
            )
        if observation.total_count <= SEARCH_RESULT_CAP:
            nodes.append(PartitionNode(interval, observation.total_count, "LEAF"))
            return observation.total_count

        start = _parse_utc_second(interval.start_utc)
        end = _parse_utc_second(interval.end_utc)
        if start == end:
            raise CandidateSourceV03Error(
                "GITHUB_SEARCH_ATOMIC_PARTITION_OVERFLOW",
                "one UTC second still exceeds the result cap",
            )
        nodes.append(PartitionNode(interval, observation.total_count, "SPLIT"))
        left, right = split_created_interval(interval)
        child_total = visit(left) + visit(right)
        if child_total != observation.total_count:
            raise CandidateSourceV03Error(
                "GITHUB_SEARCH_PARTITION_COUNT_MISMATCH",
                f"parent count {observation.total_count} != children {child_total}",
            )
        return observation.total_count

    visit(root_interval)
    return tuple(nodes)


def request_decision(
    *,
    attempt_number: int,
    http_status: int | None = None,
    transport_error: str | None = None,
    rate_limit_evidence: bool = False,
) -> RequestDecision:
    """Return the frozen action for one API request attempt."""

    if attempt_number not in {1, 2, 3}:
        raise CandidateSourceV03Error(
            "REQUEST_ATTEMPT_INVALID", "attempt_number must be 1, 2, or 3"
        )
    if (http_status is None) == (transport_error is None):
        raise CandidateSourceV03Error(
            "REQUEST_RESULT_INVALID",
            "provide exactly one of http_status or transport_error",
        )
    if http_status == 429 or (http_status == 403 and rate_limit_evidence):
        return RequestDecision("FAIL", 0, "API_RATE_LIMIT_EXHAUSTED")
    transient = (
        http_status in TRANSIENT_HTTP_STATUSES
        or transport_error in TRANSIENT_TRANSPORT_ERRORS
    )
    if transient and attempt_number < MAXIMUM_ATTEMPTS:
        return RequestDecision(
            "RETRY", RETRY_DELAYS_SECONDS[attempt_number - 1], None
        )
    if transient:
        return RequestDecision("FAIL", 0, "API_TRANSIENT_FAILURE_EXHAUSTED")
    if transport_error is not None:
        return RequestDecision("FAIL", 0, "API_PERMANENT_TRANSPORT_FAILURE")
    if http_status is not None and 200 <= http_status < 300:
        return RequestDecision("ACCEPT", 0, None)
    return RequestDecision("FAIL", 0, "API_PERMANENT_HTTP_FAILURE")


def resolve_merged_pr_episode(
    *,
    repository_id: Any,
    merged: bool,
    merged_at_utc: str | None,
    head_sha: Any,
    repair_endpoint_sha: Any,
    endpoint_parent_shas: Sequence[Any],
    pr_commit_count: Any,
) -> RepairEpisode:
    """Resolve only unambiguous immutable merged-PR topology."""

    if merged is not True or not isinstance(merged_at_utc, str) or not merged_at_utc:
        raise CandidateSourceV03Error(
            "GITHUB_PR_NOT_MERGED", "merged=true and merged_at are required"
        )
    numeric_id = _require_repository_id(repository_id)
    head = _require_sha(head_sha, label="head_sha")
    repair = _require_sha(repair_endpoint_sha, label="repair_endpoint_sha")
    if (
        isinstance(pr_commit_count, bool)
        or not isinstance(pr_commit_count, int)
        or pr_commit_count < 1
    ):
        raise CandidateSourceV03Error(
            "SOURCE_SCHEMA_DRIFT", "PR commit count must be positive integer"
        )
    parents = tuple(
        _require_sha(parent, label=f"endpoint_parent_shas[{index}]")
        for index, parent in enumerate(endpoint_parent_shas)
    )
    if len(parents) == 2:
        if parents[1] != head:
            raise CandidateSourceV03Error(
                "GITHUB_PR_ENDPOINT_PARENT_MISMATCH",
                "ordinary merge second parent must equal captured PR head",
            )
        snapshot = parents[0]
        topology = "ORDINARY_MERGE_COMMIT"
    elif len(parents) == 1 and pr_commit_count == 1:
        snapshot = parents[0]
        topology = "SINGLE_PARENT_SINGLE_COMMIT"
    elif len(parents) == 1:
        raise CandidateSourceV03Error(
            "GITHUB_PR_MERGE_TOPOLOGY_AMBIGUOUS",
            "multi-commit single-parent PR can be squash or rebase",
        )
    else:
        raise CandidateSourceV03Error(
            "GITHUB_PR_MERGE_TOPOLOGY_AMBIGUOUS",
            "merged PR endpoint must have one or two parents",
        )
    return RepairEpisode(
        canonical_candidate_id=canonical_candidate_id(
            repository_id=numeric_id,
            candidate_snapshot_commit_sha=snapshot,
            repair_commit_sha=repair,
        ),
        github_repository_id=numeric_id,
        candidate_snapshot_commit_sha=snapshot,
        repair_commit_sha=repair,
        topology=topology,
    )


def resolve_explicit_commit_episode(
    *, repository_id: Any, repair_commit_sha: Any, parent_shas: Sequence[Any]
) -> RepairEpisode:
    """Resolve an advisory commit only when its sole parent defines the range."""

    if len(parent_shas) != 1:
        raise CandidateSourceV03Error(
            "ADVISORY_COMMIT_PARENT_NOT_SINGLE",
            "explicit advisory commit must have exactly one parent",
        )
    snapshot = _require_sha(parent_shas[0], label="parent_sha")
    repair = _require_sha(repair_commit_sha, label="repair_commit_sha")
    numeric_id = _require_repository_id(repository_id)
    return RepairEpisode(
        canonical_candidate_id=canonical_candidate_id(
            repository_id=numeric_id,
            candidate_snapshot_commit_sha=snapshot,
            repair_commit_sha=repair,
        ),
        github_repository_id=numeric_id,
        candidate_snapshot_commit_sha=snapshot,
        repair_commit_sha=repair,
        topology="EXPLICIT_SINGLE_PARENT_COMMIT",
    )


def resolve_benchmark_episode(
    *,
    repository_id: Any,
    buggy_commit_sha: Any,
    fixed_commit_sha: Any,
    buggy_is_ancestor_of_fixed: bool,
) -> RepairEpisode:
    """Resolve benchmark metadata only with exact ancestry evidence."""

    if buggy_is_ancestor_of_fixed is not True:
        raise CandidateSourceV03Error(
            "BENCHMARK_REPAIR_ANCESTRY_INVALID",
            "buggy commit must be an ancestor of fixed commit",
        )
    numeric_id = _require_repository_id(repository_id)
    snapshot = _require_sha(buggy_commit_sha, label="buggy_commit_sha")
    repair = _require_sha(fixed_commit_sha, label="fixed_commit_sha")
    return RepairEpisode(
        canonical_candidate_id=canonical_candidate_id(
            repository_id=numeric_id,
            candidate_snapshot_commit_sha=snapshot,
            repair_commit_sha=repair,
        ),
        github_repository_id=numeric_id,
        candidate_snapshot_commit_sha=snapshot,
        repair_commit_sha=repair,
        topology="BENCHMARK_DECLARED_ANCESTRY",
    )


def deduplication_decision(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> str:
    """Compare complete repair ranges without missing-value equality."""

    fields = (
        "github_repository_id",
        "candidate_snapshot_commit_sha",
        "repair_commit_sha",
    )
    left_complete = (
        isinstance(left.get("github_repository_id"), int)
        and not isinstance(left.get("github_repository_id"), bool)
        and int(left["github_repository_id"]) > 0
        and all(
            isinstance(left.get(field), str)
            and SHA1_PATTERN.fullmatch(str(left[field]))
            for field in fields[1:]
        )
    )
    right_complete = (
        isinstance(right.get("github_repository_id"), int)
        and not isinstance(right.get("github_repository_id"), bool)
        and int(right["github_repository_id"]) > 0
        and all(
            isinstance(right.get(field), str)
            and SHA1_PATTERN.fullmatch(str(right[field]))
            for field in fields[1:]
        )
    )
    if left_complete and right_complete:
        if all(left[field] == right[field] for field in fields):
            return "EXACT_DUPLICATE"
        if left["github_repository_id"] != right["github_repository_id"]:
            return "DISTINCT"
        left_pr = left.get("pull_request_number")
        right_pr = right.get("pull_request_number")
        if (
            isinstance(left_pr, int)
            and not isinstance(left_pr, bool)
            and left_pr > 0
            and isinstance(right_pr, int)
            and not isinstance(right_pr, bool)
            and right_pr == left_pr
        ):
            return "IDENTITY_CONFLICT"
        if (
            left["repair_commit_sha"] == right["repair_commit_sha"]
            or left.get("patch_sha256") == right.get("patch_sha256")
            and isinstance(left.get("patch_sha256"), str)
            and SHA256_PATTERN.fullmatch(str(left["patch_sha256"]))
        ):
            return "POSSIBLE_DUPLICATE"
        return "DISTINCT"

    hints = (
        "github_repository_id",
        "repository_full_name",
        "repair_commit_sha",
        "pull_request_number",
        "patch_sha256",
    )
    if any(
        left.get(field) not in (None, "")
        and right.get(field) not in (None, "")
        and left.get(field) == right.get(field)
        for field in hints
    ):
        return "POSSIBLE_DUPLICATE"
    return "DISTINCT"


def build_candidate_provenance_index(
    candidate_source_pairs: Iterable[tuple[str, str]],
) -> list[dict[str, Any]]:
    """Preserve all source-record provenance in deterministic order."""

    grouped: dict[str, set[str]] = defaultdict(set)
    for candidate_id, record_id in candidate_source_pairs:
        if CANDIDATE_ID_PATTERN.fullmatch(candidate_id) is None:
            raise CandidateSourceV03Error(
                "CANDIDATE_ID_INVALID", f"invalid candidate ID {candidate_id!r}"
            )
        if SOURCE_RECORD_ID_PATTERN.fullmatch(record_id) is None:
            raise CandidateSourceV03Error(
                "SOURCE_RECORD_ID_INVALID", f"invalid source record ID {record_id!r}"
            )
        grouped[candidate_id].add(record_id)
    return [
        {
            "canonical_candidate_id": candidate_id,
            "source_record_ids": sorted(grouped[candidate_id]),
        }
        for candidate_id in sorted(grouped)
    ]


def raw_artifact_descriptor(data: bytes, *, media_type: str) -> dict[str, Any]:
    """Describe exact bytes using the frozen content-addressed layout."""

    if not isinstance(data, bytes) or not isinstance(media_type, str) or not media_type:
        raise CandidateSourceV03Error(
            "RAW_ARTIFACT_INVALID", "bytes and media type are required"
        )
    digest = hashlib.sha256(data).hexdigest()
    return {
        "media_type": media_type,
        "path": f"raw/sha256/{digest[:2]}/{digest[2:]}",
        "sha256": digest,
        "size_bytes": len(data),
    }


def verify_raw_artifact(data: bytes, descriptor: Mapping[str, Any]) -> None:
    """Reject any mismatch between bytes, digest, size, and canonical path."""

    expected = raw_artifact_descriptor(
        data, media_type=str(descriptor.get("media_type", ""))
    )
    if dict(descriptor) != expected:
        raise CandidateSourceV03Error(
            "RAW_ARTIFACT_HASH_MISMATCH",
            "raw artifact descriptor does not match exact bytes",
        )


def _load_object(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CandidateSourceV03Error(
            "SPECIFICATION_JSON_INVALID", f"cannot load {path}: {error}"
        ) from error
    if not isinstance(value, Mapping):
        raise CandidateSourceV03Error(
            "SPECIFICATION_JSON_INVALID", f"{path} must contain an object"
        )
    return value


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_v03_specification(
    *, v02_directory: Path, v03_directory: Path, audit_path: Path
) -> dict[str, Any]:
    """Validate the additive freeze without contacting any source."""

    expected_files = {
        "README.md",
        "amendment.json",
        "raw-capture-manifest.schema.json",
        "source-record.schema.json",
    }
    actual_files = {path.name for path in v03_directory.iterdir() if path.is_file()}
    if actual_files != expected_files:
        raise CandidateSourceV03Error(
            "SPECIFICATION_FILE_SET_INVALID",
            f"expected {sorted(expected_files)}, found {sorted(actual_files)}",
        )
    actual_v02_hashes = {
        name: _sha256_file(v02_directory / name) for name in V02_HASHES
    }
    if actual_v02_hashes != V02_HASHES:
        raise CandidateSourceV03Error(
            "V02_SPECIFICATION_HASH_MISMATCH", "a frozen v0.2 file changed"
        )
    amendment = _load_object(v03_directory / "amendment.json")
    if amendment.get("protocol_version") != PROTOCOL_VERSION:
        raise CandidateSourceV03Error(
            "SPECIFICATION_VERSION_INVALID", "v0.3 protocol version mismatch"
        )
    if amendment.get("base_protocol", {}).get("specification_hashes") != V02_HASHES:
        raise CandidateSourceV03Error(
            "V02_SPECIFICATION_HASH_MISMATCH", "amendment base hashes mismatch"
        )
    if amendment.get("execution_status") != "FROZEN_NOT_EXECUTED":
        raise CandidateSourceV03Error(
            "SPECIFICATION_EXECUTION_STATUS_INVALID", "source was marked executed"
        )
    for key in (
        "identity_fetch_performed",
        "experiment_accessed",
        "treatment_results_consulted",
    ):
        if amendment.get(key) is not False:
            raise CandidateSourceV03Error(
                "SPECIFICATION_INTEGRITY_FLAG_INVALID", f"{key} must be false"
            )
    separation = amendment.get("scientific_separation_override", {})
    forbidden = separation.get("discovery_forbidden_assignments", [])
    if set(forbidden) != FORBIDDEN_DISCOVERY_ASSIGNMENTS:
        raise CandidateSourceV03Error(
            "SCIENTIFIC_SEPARATION_INCOMPLETE",
            "forbidden discovery assignments are incomplete",
        )
    partition = amendment.get("github_created_partition_override", {})
    if (
        partition.get("field") != "created"
        or partition.get("result_cap") != SEARCH_RESULT_CAP
        or partition.get("root_interval", {}).get("start_utc_inclusive")
        != ROOT_START_UTC
        or partition.get("root_interval", {}).get("end_utc_inclusive")
        != ROOT_END_UTC
    ):
        raise CandidateSourceV03Error(
            "PARTITION_SPECIFICATION_INVALID", "created partition rules changed"
        )
    request_policy = amendment.get("request_policy_override", {})
    if request_policy.get("timeouts_seconds") != {
        "connect": 10,
        "read": 30,
        "total_per_attempt": 45,
    }:
        raise CandidateSourceV03Error(
            "REQUEST_POLICY_INVALID", "timeout policy changed"
        )
    audit = _load_object(audit_path)
    if (
        audit.get("audited_commit")
        != "715592b8b96a689f7e532d5ad211bc9b5c7d82c1"
        or audit.get("real_discovery_source_executed") is not False
        or audit.get("identity_fetch_performed") is not False
        or audit.get("treatment_results_consulted") is not False
    ):
        raise CandidateSourceV03Error(
            "AUDIT_ARTIFACT_INVALID", "pre-execution audit flags are invalid"
        )
    source_schema = _load_object(v03_directory / "source-record.schema.json")
    capture_schema = _load_object(
        v03_directory / "raw-capture-manifest.schema.json"
    )
    if source_schema.get("properties", {}).get("protocol_version", {}).get(
        "const"
    ) != PROTOCOL_VERSION:
        raise CandidateSourceV03Error(
            "SPECIFICATION_SCHEMA_INVALID", "source-record schema version mismatch"
        )
    if capture_schema.get("properties", {}).get("normalization_started", {}).get(
        "const"
    ) is not False:
        raise CandidateSourceV03Error(
            "SPECIFICATION_SCHEMA_INVALID", "capture must precede normalization"
        )
    return {
        "identity_fetch_performed": False,
        "network_accessed": False,
        "pass": True,
        "protocol_version": PROTOCOL_VERSION,
        "treatment_results_consulted": False,
        "v02_hash_count": len(V02_HASHES),
        "v03_file_count": len(expected_files),
    }
