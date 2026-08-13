"""Pure, offline rules for prospective candidate-source protocol v0.2.

This module parses already-supplied metadata and assigns deterministic
identifiers.  It deliberately contains no HTTP, git, subprocess, or model
execution path.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit


PROTOCOL_VERSION = "benchmark-selection-source-v0.2"
SOURCE_RECORD_SCHEMA = "candidate-source-record-v0.2"
SOURCE_RECORD_ID_PATTERN = re.compile(r"^CMVP-SRC-02-[0-9a-f]{64}$")
CANDIDATE_ID_PATTERN = re.compile(r"^CMVP-CAND-02-[0-9a-f]{64}$")
SHA1_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CVE_PATTERN = re.compile(r"^CVE-[0-9]{4}-[0-9]+$")
FIELD_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
BARE_VALUE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+~-]*$")
ASSIGNMENT_PATTERN = re.compile(
    r"^[ \t]*(?P<key>[a-z][a-z0-9_]*)[ \t]*=[ \t]*"
    r'''(?P<value>'[^'\\\r\n]*'|"[^"\\\r\n]*"|'''
    r"[A-Za-z0-9][A-Za-z0-9._:/@+~-]*)[ \t]*$"
)
GITHUB_NAME_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,99})$")
BUGSINPY_FIELDS = frozenset(
    {
        "buggy_commit_id",
        "fixed_commit_id",
        "python_version",
        "test_command",
        "test_file",
        "test_files",
    }
)
BUGSINPY_REQUIRED_FIELDS = frozenset({"buggy_commit_id", "fixed_commit_id"})


class SourceProtocolError(ValueError):
    """Base error carrying a stable protocol reason code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class SourceRecordRejected(SourceProtocolError):
    """A raw source object cannot be materialized as a candidate."""


class SourceBatchRejected(SourceProtocolError):
    """A source query cannot be enumerated completely and must fail closed."""


@dataclass(frozen=True)
class GitHubReference:
    """A normalized, syntactically accepted public GitHub reference."""

    kind: str
    owner: str
    repository: str
    value: str | int | None
    canonical_url: str


def canonical_json_bytes(value: Any) -> bytes:
    """Encode a value using the protocol's canonical JSON representation."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise SourceProtocolError(
            "NON_CANONICAL_IDENTITY_INPUT", f"identity input is not JSON: {error}"
        ) from error


def _digest_identifier(prefix: str, value: Mapping[str, Any]) -> str:
    return prefix + hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def source_record_id(
    *, source_id: str, source_revision: str, source_native_identity: Mapping[str, Any]
) -> str:
    """Return an unlimited, deterministic ID within one immutable source."""

    if (
        not source_id
        or not isinstance(source_revision, str)
        or not (
            SHA1_PATTERN.fullmatch(source_revision)
            or SHA256_PATTERN.fullmatch(source_revision)
        )
        or not source_native_identity
    ):
        raise SourceProtocolError(
            "SOURCE_IDENTITY_FIELD_MISSING",
            "source_id, immutable 40/64-hex source_revision, and native identity are required",
        )
    envelope = {
        "protocol_version": PROTOCOL_VERSION,
        "source_id": source_id,
        "source_native_identity": source_native_identity,
        "source_revision": source_revision,
    }
    return _digest_identifier("CMVP-SRC-02-", envelope)


def _require_repository_id(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SourceRecordRejected(
            "GITHUB_REPOSITORY_ID_MISSING",
            "a positive GitHub repository numeric ID is required",
        )
    return value


def _require_sha(value: Any, *, code: str, label: str) -> str:
    if not isinstance(value, str) or SHA1_PATTERN.fullmatch(value) is None:
        raise SourceRecordRejected(code, f"{label} must be a lowercase 40-hex SHA")
    return value


def canonical_candidate_id(*, repository_id: Any, repair_commit_sha: Any) -> str:
    """Assign a stable candidate ID from positive immutable episode identity."""

    numeric_id = _require_repository_id(repository_id)
    repair_sha = _require_sha(
        repair_commit_sha,
        code="REPAIR_ANCHOR_MISSING",
        label="repair_commit_sha",
    )
    envelope = {
        "github_repository_id": numeric_id,
        "protocol_version": PROTOCOL_VERSION,
        "repair_commit_sha": repair_sha,
    }
    return _digest_identifier("CMVP-CAND-02-", envelope)


def parse_bugsinpy_metadata(
    text: str,
    *,
    allowed_fields: frozenset[str] = BUGSINPY_FIELDS,
    required_fields: frozenset[str] = BUGSINPY_REQUIRED_FIELDS,
) -> dict[str, str]:
    """Parse the frozen non-executable BugsInPy assignment grammar."""

    if not isinstance(text, str) or "\x00" in text:
        raise SourceRecordRejected(
            "BUGSINPY_MALFORMED_LINE", "metadata must be NUL-free UTF-8 text"
        )
    values: dict[str, str] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = ASSIGNMENT_PATTERN.fullmatch(line)
        if match is None:
            raise SourceRecordRejected(
                "BUGSINPY_MALFORMED_LINE",
                f"line {line_number} does not match the frozen assignment grammar",
            )
        key = match.group("key")
        if key not in allowed_fields:
            raise SourceRecordRejected(
                "BUGSINPY_UNKNOWN_FIELD",
                f"line {line_number} contains non-whitelisted field {key!r}",
            )
        if key in values:
            raise SourceRecordRejected(
                "BUGSINPY_DUPLICATE_FIELD",
                f"line {line_number} repeats field {key!r}",
            )
        raw_value = match.group("value")
        if raw_value[:1] in {"'", '"'}:
            value = raw_value[1:-1]
        else:
            value = raw_value
        if not value or any(character in value for character in ("$", "`", "\\")):
            raise SourceRecordRejected(
                "BUGSINPY_UNSAFE_VALUE",
                f"line {line_number} contains an empty or executable value",
            )
        values[key] = value
    missing = sorted(required_fields - values.keys())
    if missing:
        raise SourceRecordRejected(
            "BUGSINPY_REQUIRED_FIELD_MISSING",
            "missing required metadata fields: " + ", ".join(missing),
        )
    for commit_field in ("buggy_commit_id", "fixed_commit_id"):
        _require_sha(
            values[commit_field],
            code="BUGSINPY_INVALID_COMMIT",
            label=commit_field,
        )
    return values


def parse_github_reference(url: Any) -> GitHubReference:
    """Normalize only the repository, commit, and pull URL forms in v0.2."""

    if not isinstance(url, str) or not url:
        raise SourceRecordRejected(
            "GITHUB_REFERENCE_MALFORMED", "GitHub reference must be a URL string"
        )
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as error:
        raise SourceRecordRejected(
            "GITHUB_REFERENCE_MALFORMED", f"invalid GitHub URL: {error}"
        ) from error
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").casefold() != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
    ):
        raise SourceRecordRejected(
            "GITHUB_REFERENCE_MALFORMED",
            "reference must be credential-free canonical HTTPS github.com URL",
        )
    if "//" in parsed.path:
        raise SourceRecordRejected(
            "GITHUB_REFERENCE_MALFORMED",
            "reference path cannot contain empty segments",
        )
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) not in {2, 4}:
        raise SourceRecordRejected(
            "GITHUB_REFERENCE_UNSUPPORTED",
            "only repository, commit, and pull request URLs are accepted",
        )
    owner = parts[0]
    repository = parts[1]
    if len(parts) == 2 and repository.endswith(".git"):
        repository = repository[:-4]
    if (
        GITHUB_NAME_PATTERN.fullmatch(owner) is None
        or GITHUB_NAME_PATTERN.fullmatch(repository) is None
    ):
        raise SourceRecordRejected(
            "GITHUB_REFERENCE_MALFORMED", "invalid GitHub owner or repository name"
        )
    root = f"https://github.com/{owner}/{repository}"
    if len(parts) == 2:
        return GitHubReference("REPOSITORY", owner, repository, None, root)
    reference_kind, raw_value = parts[2:]
    if reference_kind == "commit" and SHA1_PATTERN.fullmatch(raw_value.casefold()):
        value = raw_value.casefold()
        return GitHubReference("COMMIT", owner, repository, value, f"{root}/commit/{value}")
    if reference_kind == "pull" and raw_value.isascii() and raw_value.isdigit():
        value = int(raw_value)
        if value > 0 and str(value) == raw_value:
            return GitHubReference("PULL_REQUEST", owner, repository, value, f"{root}/pull/{value}")
    raise SourceRecordRejected(
        "GITHUB_REFERENCE_UNSUPPORTED",
        "reference is not an exact commit or positive canonical pull-request URL",
    )


def normalize_pypi_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceRecordRejected(
            "ADVISORY_MALFORMED", "PyPI package name must be a non-empty string"
        )
    normalized = re.sub(r"[-_.]+", "-", value.strip()).casefold()
    if re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", normalized) is None:
        raise SourceRecordRejected(
            "ADVISORY_MALFORMED", f"invalid PyPI package name {value!r}"
        )
    return normalized


def normalize_github_repository(repository: Mapping[str, Any]) -> dict[str, Any]:
    """Require numeric identity while retaining names only as capture metadata."""

    repository_id = _require_repository_id(repository.get("id"))
    owner = repository.get("owner")
    name = repository.get("name")
    url = repository.get("html_url")
    visibility = repository.get("visibility")
    if not all(isinstance(value, str) and value for value in (owner, name, url)):
        raise SourceRecordRejected(
            "GITHUB_REPOSITORY_METADATA_MISSING",
            "capture-time owner, name, and html_url are required",
        )
    if visibility != "public":
        raise SourceRecordRejected(
            "GITHUB_REPOSITORY_NOT_PUBLIC", "repository visibility must be public"
        )
    parsed = parse_github_reference(url)
    if parsed.kind != "REPOSITORY":
        raise SourceRecordRejected(
            "GITHUB_REPOSITORY_METADATA_MISSING", "html_url must identify a repository"
        )
    if parsed.owner.casefold() != owner.casefold() or parsed.repository.casefold() != name.casefold():
        raise SourceRecordRejected(
            "GITHUB_REPOSITORY_METADATA_MISMATCH",
            "owner, name, and html_url do not identify the same repository",
        )
    return {
        "id": repository_id,
        "owner": owner,
        "name": name,
        "html_url": parsed.canonical_url,
        "visibility": "public",
    }


def github_pull_request_episode(
    pull_request: Mapping[str, Any], repository: Mapping[str, Any]
) -> dict[str, Any]:
    """Materialize one merged PR using base.sha as the candidate snapshot."""

    normalized_repository = normalize_github_repository(repository)
    number = pull_request.get("number")
    if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
        raise SourceRecordRejected(
            "GITHUB_PR_DETAIL_INCOMPLETE", "pull-request number is required"
        )
    if pull_request.get("merged") is not True:
        raise SourceRecordRejected(
            "GITHUB_PR_NOT_MERGED", "pull request must be merged"
        )
    base = pull_request.get("base")
    head = pull_request.get("head")
    if not isinstance(base, Mapping) or not isinstance(head, Mapping):
        raise SourceRecordRejected(
            "GITHUB_PR_DETAIL_INCOMPLETE", "base and head objects are required"
        )
    base_sha = _require_sha(
        base.get("sha"), code="GITHUB_PR_DETAIL_INCOMPLETE", label="base.sha"
    )
    head_sha = _require_sha(
        head.get("sha"), code="GITHUB_PR_DETAIL_INCOMPLETE", label="head.sha"
    )
    merge_sha = _require_sha(
        pull_request.get("merge_commit_sha"),
        code="GITHUB_PR_DETAIL_INCOMPLETE",
        label="merge_commit_sha",
    )
    repository_id = normalized_repository["id"]
    return {
        "canonical_candidate_id": canonical_candidate_id(
            repository_id=repository_id, repair_commit_sha=merge_sha
        ),
        "candidate_snapshot_commit_sha": base_sha,
        "github_repository_id": repository_id,
        "head_commit_sha": head_sha,
        "pull_request_number": number,
        "repair_commit_sha": merge_sha,
        "repository_capture_metadata": normalized_repository,
    }


def _advisory_packages(advisory: Mapping[str, Any]) -> tuple[str, ...]:
    affected = advisory.get("affected")
    if not isinstance(affected, list):
        raise SourceRecordRejected(
            "ADVISORY_MALFORMED", "affected must be an array"
        )
    packages: set[str] = set()
    for entry in affected:
        if not isinstance(entry, Mapping):
            raise SourceRecordRejected(
                "ADVISORY_MALFORMED", "each affected entry must be an object"
            )
        package = entry.get("package")
        if not isinstance(package, Mapping):
            raise SourceRecordRejected(
                "ADVISORY_MALFORMED", "affected.package must be an object"
            )
        if package.get("ecosystem") == "PyPI":
            packages.add(normalize_pypi_name(package.get("name")))
    if not packages:
        raise SourceRecordRejected(
            "ADVISORY_NO_PYPI_PACKAGE", "advisory has no PyPI affected package"
        )
    return tuple(sorted(packages))


def _advisory_is_malware(advisory: Mapping[str, Any], advisory_path: str) -> bool:
    database_specific = advisory.get("database_specific", {})
    if not isinstance(database_specific, Mapping):
        raise SourceRecordRejected(
            "ADVISORY_MALFORMED", "database_specific must be an object"
        )
    malware = database_specific.get("malware", False)
    if not isinstance(malware, bool):
        raise SourceRecordRejected(
            "ADVISORY_MALFORMED", "database_specific.malware must be boolean"
        )
    path = Path(advisory_path)
    path_is_malware = len(path.parts) >= 2 and path.parts[:2] == (
        "advisories",
        "malware",
    )
    return malware or path_is_malware


def advisory_repair_episodes(
    advisory: Mapping[str, Any],
    *,
    advisory_path: str,
    resolved_references: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Build advisory×repository repair episodes from explicit resolutions."""

    advisory_id = advisory.get("id")
    if not isinstance(advisory_id, str) or not advisory_id:
        raise SourceRecordRejected(
            "ADVISORY_MALFORMED", "advisory id is required"
        )
    withdrawn = advisory.get("withdrawn")
    if withdrawn is not None:
        if not isinstance(withdrawn, str) or not withdrawn:
            raise SourceRecordRejected(
                "ADVISORY_MALFORMED", "withdrawn must be null, absent, or timestamp"
            )
        raise SourceRecordRejected("ADVISORY_WITHDRAWN", "advisory is withdrawn")
    if _advisory_is_malware(advisory, advisory_path):
        raise SourceRecordRejected("ADVISORY_MALWARE", "advisory is malware")
    if re.fullmatch(r"advisories/github-reviewed/.+\.json", advisory_path) is None:
        raise SourceRecordRejected(
            "ADVISORY_SOURCE_PATH_INVALID",
            "advisory path is outside the frozen github-reviewed tree",
        )
    aliases = advisory.get("aliases")
    if not isinstance(aliases, list) or not all(
        isinstance(alias, str) for alias in aliases
    ):
        raise SourceRecordRejected(
            "ADVISORY_MALFORMED", "aliases must be an array of strings"
        )
    if not any(CVE_PATTERN.fullmatch(alias) for alias in aliases):
        raise SourceRecordRejected(
            "ADVISORY_CVE_ALIAS_MISSING",
            "advisory has no exact CVE alias",
        )
    packages = _advisory_packages(advisory)
    references = advisory.get("references")
    if not isinstance(references, list):
        raise SourceRecordRejected(
            "ADVISORY_MALFORMED", "references must be an array"
        )

    grouped: dict[tuple[int, str], dict[str, Any]] = {}
    accepted_repair_reference = False
    for reference_record in references:
        if not isinstance(reference_record, Mapping):
            raise SourceRecordRejected(
                "ADVISORY_MALFORMED", "each reference must be an object"
            )
        url = reference_record.get("url")
        if not isinstance(url, str):
            raise SourceRecordRejected(
                "ADVISORY_MALFORMED", "reference.url must be a string"
            )
        if (urlsplit(url).hostname or "").casefold() != "github.com":
            continue
        try:
            reference = parse_github_reference(url)
        except SourceRecordRejected as error:
            raise SourceRecordRejected(
                "ADVISORY_GITHUB_REFERENCE_MALFORMED", str(error)
            ) from error
        if reference.kind == "REPOSITORY":
            continue
        accepted_repair_reference = True
        resolution = resolved_references.get(reference.canonical_url)
        if not isinstance(resolution, Mapping):
            raise SourceRecordRejected(
                "ADVISORY_REPAIR_REFERENCE_UNRESOLVED",
                f"no exact resolution for {reference.canonical_url}",
            )
        repository = resolution.get("repository")
        if not isinstance(repository, Mapping):
            raise SourceRecordRejected(
                "GITHUB_REPOSITORY_METADATA_MISSING",
                "resolved advisory reference lacks repository metadata",
            )
        normalized_repository = normalize_github_repository(repository)
        repository_id = normalized_repository["id"]
        if (
            reference.owner.casefold()
            != str(normalized_repository["owner"]).casefold()
            or reference.repository.casefold()
            != str(normalized_repository["name"]).casefold()
        ):
            raise SourceRecordRejected(
                "ADVISORY_REPAIR_REFERENCE_MISMATCH",
                "resolved repository metadata does not match reference path",
            )
        if reference.kind == "COMMIT":
            commit_sha = _require_sha(
                resolution.get("commit_sha"),
                code="ADVISORY_REPAIR_REFERENCE_UNRESOLVED",
                label="resolved commit SHA",
            )
            if commit_sha != reference.value:
                raise SourceRecordRejected(
                    "ADVISORY_REPAIR_REFERENCE_MISMATCH",
                    "resolved commit does not match explicit reference",
                )
            parent_shas = resolution.get("parent_shas")
            if not isinstance(parent_shas, list) or len(parent_shas) != 1:
                raise SourceRecordRejected(
                    "ADVISORY_COMMIT_PARENT_NOT_SINGLE",
                    "explicit repair commit must have exactly one captured parent",
                )
            snapshot_sha = _require_sha(
                parent_shas[0],
                code="ADVISORY_COMMIT_PARENT_NOT_SINGLE",
                label="repair commit parent",
            )
            pull_request_number = None
            repair_sha = commit_sha
        else:
            pull_request = resolution.get("pull_request")
            if not isinstance(pull_request, Mapping):
                raise SourceRecordRejected(
                    "ADVISORY_PR_DETAIL_INCOMPLETE",
                    "pull-request detail capture is required",
                )
            episode = github_pull_request_episode(pull_request, repository)
            if episode["pull_request_number"] != reference.value:
                raise SourceRecordRejected(
                    "ADVISORY_REPAIR_REFERENCE_MISMATCH",
                    "resolved PR number does not match explicit reference",
                )
            snapshot_sha = episode["candidate_snapshot_commit_sha"]
            repair_sha = episode["repair_commit_sha"]
            pull_request_number = episode["pull_request_number"]

        key = (repository_id, repair_sha)
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = {
                "advisory_id": advisory_id,
                "canonical_candidate_id": canonical_candidate_id(
                    repository_id=repository_id, repair_commit_sha=repair_sha
                ),
                "candidate_snapshot_commit_sha": snapshot_sha,
                "github_repository_id": repository_id,
                "package_names": list(packages),
                "pull_request_numbers": (
                    [] if pull_request_number is None else [pull_request_number]
                ),
                "repair_commit_sha": repair_sha,
                "repair_reference_urls": [reference.canonical_url],
                "repository_capture_metadata": normalized_repository,
            }
        else:
            if existing["candidate_snapshot_commit_sha"] != snapshot_sha:
                raise SourceRecordRejected(
                    "ADVISORY_REPAIR_EPISODE_CONFLICT",
                    "equal repair identity produced different pre-repair snapshots",
                )
            existing["repair_reference_urls"].append(reference.canonical_url)
            if (
                pull_request_number is not None
                and pull_request_number not in existing["pull_request_numbers"]
            ):
                existing["pull_request_numbers"].append(pull_request_number)

    if not accepted_repair_reference:
        raise SourceRecordRejected(
            "ADVISORY_NO_ACCEPTED_REPAIR_REFERENCE",
            "advisory has no explicit accepted GitHub commit or PR reference",
        )
    episodes = list(grouped.values())
    for episode in episodes:
        episode["pull_request_numbers"].sort()
        episode["repair_reference_urls"].sort()
    return sorted(
        episodes,
        key=lambda episode: (
            episode["github_repository_id"],
            episode["repair_commit_sha"],
        ),
    )


def _normalized_hint(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().rstrip("/").casefold()


def deduplication_decision(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> str:
    """Compare episodes without treating absent values as wildcards."""

    left_repository = left.get("github_repository_id")
    right_repository = right.get("github_repository_id")
    valid_left_repository = (
        isinstance(left_repository, int)
        and not isinstance(left_repository, bool)
        and left_repository > 0
    )
    valid_right_repository = (
        isinstance(right_repository, int)
        and not isinstance(right_repository, bool)
        and right_repository > 0
    )
    left_sha = left.get("repair_commit_sha")
    right_sha = right.get("repair_commit_sha")
    valid_left_sha = isinstance(left_sha, str) and SHA1_PATTERN.fullmatch(left_sha)
    valid_right_sha = isinstance(right_sha, str) and SHA1_PATTERN.fullmatch(right_sha)
    left_pr = left.get("pull_request_number")
    right_pr = right.get("pull_request_number")
    valid_left_pr = isinstance(left_pr, int) and not isinstance(left_pr, bool) and left_pr > 0
    valid_right_pr = isinstance(right_pr, int) and not isinstance(right_pr, bool) and right_pr > 0

    if valid_left_repository and valid_right_repository:
        if left_repository != right_repository:
            return "DISTINCT"
        same_sha = valid_left_sha and valid_right_sha and left_sha == right_sha
        same_pr = valid_left_pr and valid_right_pr and left_pr == right_pr
        if same_sha or same_pr:
            if same_pr and valid_left_sha and valid_right_sha and left_sha != right_sha:
                return "IDENTITY_CONFLICT"
            return "EXACT_DUPLICATE"
        if valid_left_sha and valid_right_sha and valid_left_pr and valid_right_pr:
            return "DISTINCT"
        return "POSSIBLE_DUPLICATE"

    mutable_keys = (
        "repository_full_name",
        "repository_url",
    )
    mutable_match = any(
        _normalized_hint(left.get(key)) is not None
        and _normalized_hint(left.get(key)) == _normalized_hint(right.get(key))
        for key in mutable_keys
    )
    repair_hint_match = valid_left_sha and valid_right_sha and left_sha == right_sha
    pr_hint_match = valid_left_pr and valid_right_pr and left_pr == right_pr
    if mutable_match or repair_hint_match or pr_hint_match:
        return "POSSIBLE_DUPLICATE"
    return "DISTINCT"


def validate_github_search_page(
    payload: Mapping[str, Any], *, expected_total_count: int | None = None
) -> tuple[int, Sequence[Any]]:
    """Fail a query closed on truncation, cap overflow, or count drift."""

    incomplete = payload.get("incomplete_results")
    if not isinstance(incomplete, bool):
        raise SourceBatchRejected(
            "GITHUB_SEARCH_RESPONSE_MALFORMED",
            "incomplete_results must be present and boolean",
        )
    if incomplete:
        raise SourceBatchRejected(
            "GITHUB_SEARCH_INCOMPLETE_RESULTS",
            "incomplete_results=true requires query-level failure",
        )
    total_count = payload.get("total_count")
    if (
        isinstance(total_count, bool)
        or not isinstance(total_count, int)
        or total_count < 0
    ):
        raise SourceBatchRejected(
            "GITHUB_SEARCH_RESPONSE_MALFORMED",
            "total_count must be a non-negative integer",
        )
    if total_count > 1000:
        raise SourceBatchRejected(
            "GITHUB_SEARCH_RESULT_CAP_EXCEEDED",
            "total_count exceeds the frozen 1,000-result ceiling",
        )
    if expected_total_count is not None and total_count != expected_total_count:
        raise SourceBatchRejected(
            "GITHUB_SEARCH_COUNT_DRIFT",
            "total_count changed during the capture transaction",
        )
    items = payload.get("items")
    if not isinstance(items, list) or len(items) > 100:
        raise SourceBatchRejected(
            "GITHUB_SEARCH_RESPONSE_MALFORMED",
            "items must be an array of at most 100 entries",
        )
    return total_count, items


def build_source_record(
    *,
    record_id: str,
    source_id: str,
    source_revision: Mapping[str, str],
    source_native_identity: Mapping[str, Any],
    raw_artifact: Mapping[str, str],
    disposition: str,
    candidate_links: Sequence[Mapping[str, Any]] = (),
    rejection_reason_codes: Sequence[str] = (),
) -> dict[str, Any]:
    """Create a source record while enforcing final-disposition invariants."""

    if SOURCE_RECORD_ID_PATTERN.fullmatch(record_id) is None:
        raise SourceProtocolError("SOURCE_RECORD_ID_INVALID", "invalid source record ID")
    revision_kind = source_revision.get("kind")
    revision_value = source_revision.get("value")
    revision_valid = (
        revision_kind == "GIT_COMMIT"
        and isinstance(revision_value, str)
        and SHA1_PATTERN.fullmatch(revision_value) is not None
    ) or (
        revision_kind == "VERSIONED_API_CAPTURE"
        and isinstance(revision_value, str)
        and SHA256_PATTERN.fullmatch(revision_value) is not None
    )
    if not revision_valid:
        raise SourceProtocolError(
            "SOURCE_REVISION_INVALID", "source revision is not an immutable hash"
        )
    expected_record_id = source_record_id(
        source_id=source_id,
        source_revision=str(revision_value),
        source_native_identity=source_native_identity,
    )
    if record_id != expected_record_id:
        raise SourceProtocolError(
            "SOURCE_RECORD_ID_MISMATCH",
            "source record ID does not match its canonical identity envelope",
        )
    raw_path = raw_artifact.get("path")
    raw_sha = raw_artifact.get("sha256")
    if (
        not isinstance(raw_path, str)
        or not raw_path
        or Path(raw_path).is_absolute()
        or ".." in Path(raw_path).parts
        or not isinstance(raw_sha, str)
        or SHA256_PATTERN.fullmatch(raw_sha) is None
    ):
        raise SourceProtocolError(
            "RAW_ARTIFACT_INVALID", "raw artifact path and SHA-256 are required"
        )
    if disposition not in {"MATERIALIZED", "SOURCE_REJECTED"}:
        raise SourceProtocolError("SOURCE_DISPOSITION_INVALID", "invalid disposition")
    if disposition == "MATERIALIZED" and (
        not candidate_links or rejection_reason_codes
    ):
        raise SourceProtocolError(
            "SOURCE_DISPOSITION_INVALID",
            "MATERIALIZED requires links and no rejection reasons",
        )
    if disposition == "SOURCE_REJECTED" and (
        candidate_links or not rejection_reason_codes
    ):
        raise SourceProtocolError(
            "SOURCE_DISPOSITION_INVALID",
            "SOURCE_REJECTED requires reasons and no candidate links",
        )
    for link in candidate_links:
        repository_id = link.get("github_repository_id")
        repair_sha = link.get("repair_commit_sha")
        snapshot_sha = link.get("candidate_snapshot_commit_sha")
        candidate_id = link.get("canonical_candidate_id")
        expected_candidate_id = canonical_candidate_id(
            repository_id=repository_id, repair_commit_sha=repair_sha
        )
        if (
            candidate_id != expected_candidate_id
            or not isinstance(snapshot_sha, str)
            or SHA1_PATTERN.fullmatch(snapshot_sha) is None
        ):
            raise SourceProtocolError(
                "CANDIDATE_LINK_INVALID",
                "candidate link lacks matching canonical identity or snapshot",
            )
    return {
        "candidate_links": list(candidate_links),
        "disposition": disposition,
        "experiment_accessed": False,
        "protocol_version": PROTOCOL_VERSION,
        "raw_artifact": dict(raw_artifact),
        "rejection_reason_codes": list(rejection_reason_codes),
        "schema": SOURCE_RECORD_SCHEMA,
        "source_id": source_id,
        "source_native_identity": dict(source_native_identity),
        "source_record_id": record_id,
        "source_revision": dict(source_revision),
        "treatment_results_consulted": False,
    }


def validate_specification_directory(directory: Path) -> dict[str, Any]:
    """Statically validate the frozen v0.2 files without source access."""

    required = {
        "README.md",
        "protocol.json",
        "source-record.schema.json",
        "source-rejection-codes.json",
        "repository-repair-tasks.json",
        "security-advisory-repairs.json",
        "trust-boundary-issues-prs.json",
        "source-priority-deduplication.json",
    }
    actual = {path.name for path in directory.iterdir() if path.is_file()}
    if actual != required:
        raise SourceProtocolError(
            "SPECIFICATION_FILE_SET_INVALID",
            f"expected {sorted(required)}, found {sorted(actual)}",
        )

    def load(name: str) -> Mapping[str, Any]:
        try:
            value = json.loads((directory / name).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SourceProtocolError(
                "SPECIFICATION_JSON_INVALID", f"cannot read {name}: {error}"
            ) from error
        if not isinstance(value, Mapping):
            raise SourceProtocolError(
                "SPECIFICATION_JSON_INVALID", f"{name} must contain an object"
            )
        return value

    documents = [
        load(name)
        for name in sorted(required - {"README.md", "source-record.schema.json"})
    ]
    for document in documents:
        if document.get("protocol_version") != PROTOCOL_VERSION:
            raise SourceProtocolError(
                "SPECIFICATION_VERSION_INVALID", "protocol version mismatch"
            )
        if document.get("execution_status") != "FROZEN_NOT_EXECUTED":
            raise SourceProtocolError(
                "SPECIFICATION_EXECUTION_STATUS_INVALID",
                "all v0.2 documents must remain FROZEN_NOT_EXECUTED",
            )
        if document.get("identity_fetch_performed") is not False:
            raise SourceProtocolError(
                "SPECIFICATION_IDENTITY_FLAG_INVALID",
                "identity_fetch_performed must be false",
            )
        if document.get("treatment_results_consulted") is not False:
            raise SourceProtocolError(
                "SPECIFICATION_OUTCOME_FLAG_INVALID",
                "treatment_results_consulted must be false",
            )

    repository_source = load("repository-repair-tasks.json")
    advisory_source = load("security-advisory-repairs.json")
    github_source = load("trust-boundary-issues-prs.json")
    if repository_source.get("source", {}).get("revision") != (
        "11c5f1eea954a42132cfd06bf257766a7963e0fd"
    ):
        raise SourceProtocolError(
            "SPECIFICATION_SOURCE_REVISION_INVALID", "BugsInPy revision changed"
        )
    if advisory_source.get("source", {}).get("revision") != (
        "bfef29f8e04ad5037181f98a990572d825dff579"
    ):
        raise SourceProtocolError(
            "SPECIFICATION_SOURCE_REVISION_INVALID", "advisory revision changed"
        )
    queries = github_source.get("queries")
    if not isinstance(queries, list) or len(queries) != 8:
        raise SourceProtocolError(
            "SPECIFICATION_QUERY_SET_INVALID", "exactly eight queries are required"
        )
    for query in queries:
        if not isinstance(query, Mapping) or "is:public" not in str(query.get("query")):
            raise SourceProtocolError(
                "SPECIFICATION_QUERY_SCOPE_INVALID",
                "every GitHub query must explicitly require public visibility",
            )
    return {
        "identity_fetch_performed": False,
        "network_accessed": False,
        "pass": True,
        "protocol_version": PROTOCOL_VERSION,
        "specification_file_count": len(required),
        "treatment_results_consulted": False,
    }
