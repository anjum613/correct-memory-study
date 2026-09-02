"""Executable source evidence and one-way pairing validation gates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
from typing import Any, Mapping, Sequence

from cmpilot.source_pairing import (
    CONFIRMATORY_FOCAL_SAFETY_LEVELS,
    FOCAL_SAFETY_LEVELS,
    SourcePairingError,
    canonical_json,
    sha256_bytes,
    stable_record_hash,
    validate_pstar,
)
from cmpilot.susvibes_feasibility import DEVELOPMENT_IDS, tree_sha256


SOURCE_ENTRY_REQUIRED_FIELDS = frozenset(
    {
        "source_id",
        "source_tier_by_target",
        "repository_url",
        "repository_commit",
        "commit_timestamp",
        "commit_timestamp_epoch",
        "license",
        "language",
        "build_system",
        "environment",
        "source_task_description",
        "source_task_provenance",
        "source_file",
        "source_symbol",
        "source_implementation_or_patch",
        "operation_class",
        "API_sequence",
        "AST_signature",
        "normalized_token_signature",
        "type_or_data_role_signature",
        "source_semantic_vector",
        "source_visible_libraries",
        "source_test_paths",
        "source_test_command",
        "source_test_result",
        "source_build",
        "source_task_test",
        "focal_source_safety",
        "source_environment_hash",
        "source_artifact_hashes",
        "available_before_target_B",
        "reconstruction",
    }
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_INFRASTRUCTURE_PATTERNS = tuple(
    re.compile(pattern, re.I | re.S)
    for pattern in (
        r"No module named",
        r"command not found",
        r"No such file or directory",
        r"could not resolve host",
        r"temporary failure in name resolution",
        r"connection refused",
        r"failed during test collection",
        r"collected 0 items",
        r"DeprecationWarning:.*(?:was deprecated|no longer supported)",
    )
)


class SourceValidationError(SourcePairingError):
    """Executable source evidence failed a fail-closed validation."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_command_result(
    *, exit_code: int | None, timed_out: bool, stdout: bytes, stderr: bytes
) -> str:
    if timed_out or exit_code is None:
        return "INFRASTRUCTURE_INVALID"
    combined = stdout + b"\n" + stderr
    decoded = combined.decode("utf-8", errors="replace")
    if exit_code == 0:
        return "PASS"
    if any(pattern.search(decoded) for pattern in _INFRASTRUCTURE_PATTERNS):
        return "INFRASTRUCTURE_INVALID"
    return "FAIL"


def run_evidence_command(
    command: Sequence[str],
    *,
    cwd: Path,
    environment_descriptor: Mapping[str, Any],
    timeout_seconds: int = 300,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if not command or not all(isinstance(value, str) and value for value in command):
        raise SourceValidationError("evidence command must be a non-empty argv")
    working = Path(cwd).resolve(strict=True)
    if not working.is_dir() or working.is_symlink():
        raise SourceValidationError("evidence working directory must be real")
    started_utc = _utc_now()
    started = time.monotonic()
    process = subprocess.Popen(
        list(command),
        cwd=working,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=None if environment is None else dict(environment),
        start_new_session=True,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
    elapsed = time.monotonic() - started
    finished_utc = _utc_now()
    classification = classify_command_result(
        exit_code=process.returncode,
        timed_out=timed_out,
        stdout=stdout,
        stderr=stderr,
    )
    return {
        "command": list(command),
        "working_directory_role": "PINNED_SOURCE_MATERIALIZATION",
        "environment": dict(environment_descriptor),
        "environment_sha256": stable_record_hash(environment_descriptor),
        "started_at_utc": started_utc,
        "finished_at_utc": finished_utc,
        "runtime_seconds": round(elapsed, 6),
        "timeout_seconds": timeout_seconds,
        "timed_out": timed_out,
        "exit_code": process.returncode,
        "stdout_utf8": stdout.decode("utf-8", errors="replace"),
        "stderr_utf8": stderr.decode("utf-8", errors="replace"),
        "stdout_sha256": sha256_bytes(stdout),
        "stderr_sha256": sha256_bytes(stderr),
        "classification": classification,
    }


def git_output(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(Path(repository)), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise SourceValidationError(
            f"git evidence command failed: {arguments}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def git_repository_evidence(
    repository: Path, *, expected_url: str, expected_commit: str
) -> dict[str, Any]:
    repo = Path(repository).resolve(strict=True)
    actual_commit = git_output(repo, "rev-parse", "HEAD")
    if actual_commit != expected_commit or not _SHA1.fullmatch(actual_commit):
        raise SourceValidationError("source checkout commit mismatch")
    status = git_output(repo, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise SourceValidationError("source checkout is dirty")
    remote = git_output(repo, "remote", "get-url", "origin")
    normalized_remote = remote.removesuffix("/").removesuffix(".git")
    normalized_expected = expected_url.removesuffix("/").removesuffix(".git")
    if normalized_remote != normalized_expected:
        raise SourceValidationError("source repository URL mismatch")
    timestamp_epoch = int(git_output(repo, "show", "-s", "--format=%ct", "HEAD"))
    timestamp = git_output(repo, "show", "-s", "--format=%cI", "HEAD")
    tree_object = git_output(repo, "rev-parse", "HEAD^{tree}")
    return {
        "repository_url": expected_url,
        "repository_commit": actual_commit,
        "commit_timestamp_epoch": timestamp_epoch,
        "commit_timestamp": timestamp,
        "git_tree_object_sha1": tree_object,
        "git_status": "CLEAN",
    }


def validate_timestamp(source_epoch: int, target_epoch: int) -> None:
    if not isinstance(source_epoch, int) or not isinstance(target_epoch, int):
        raise SourceValidationError("timestamps must be integer Unix seconds")
    if source_epoch > target_epoch:
        raise SourceValidationError("source commit is later than target B")


def validate_focal_safety(value: Mapping[str, Any], *, confirmatory: bool) -> None:
    required = {
        "classification",
        "level",
        "pstar",
        "evidence_command",
        "evidence_paths",
        "evidence_hashes",
        "derived_without_target_oracle",
        "scope",
    }
    if set(value) != required:
        raise SourceValidationError("focal source safety fields changed")
    level = value["level"]
    if level not in FOCAL_SAFETY_LEVELS:
        raise SourceValidationError("invalid focal source safety level")
    if confirmatory and level not in CONFIRMATORY_FOCAL_SAFETY_LEVELS:
        raise SourceValidationError("static-only source safety is development-only")
    if value["classification"] != "PASS":
        raise SourceValidationError("focal source safety did not pass")
    if value["derived_without_target_oracle"] is not True:
        raise SourceValidationError("focal source safety used target oracle data")
    if value["scope"] != "FOCAL_SOURCE_SAFETY_NOT_GLOBAL_SECURITY":
        raise SourceValidationError("focal source safety scope is overstated")
    validate_pstar(value["pstar"])
    if not isinstance(value["evidence_command"], list) or not value["evidence_command"]:
        raise SourceValidationError("focal safety lacks executable command")
    if not isinstance(value["evidence_paths"], list) or not value["evidence_paths"]:
        raise SourceValidationError("focal safety lacks evidence paths")
    hashes = value["evidence_hashes"]
    if not isinstance(hashes, dict) or not hashes or any(
        not _SHA256.fullmatch(str(digest)) for digest in hashes.values()
    ):
        raise SourceValidationError("focal safety evidence hashes are invalid")


def _validate_command_evidence(value: Mapping[str, Any], name: str) -> None:
    required = {
        "command",
        "working_directory_role",
        "environment",
        "environment_sha256",
        "started_at_utc",
        "finished_at_utc",
        "runtime_seconds",
        "timeout_seconds",
        "timed_out",
        "exit_code",
        "stdout_utf8",
        "stderr_utf8",
        "stdout_sha256",
        "stderr_sha256",
        "classification",
    }
    if set(value) != required:
        raise SourceValidationError(f"{name} command evidence fields changed")
    if stable_record_hash(value["environment"]) != value["environment_sha256"]:
        raise SourceValidationError(f"{name} environment hash mismatch")
    if sha256_bytes(str(value["stdout_utf8"]).encode("utf-8")) != value["stdout_sha256"]:
        raise SourceValidationError(f"{name} stdout hash mismatch")
    if sha256_bytes(str(value["stderr_utf8"]).encode("utf-8")) != value["stderr_sha256"]:
        raise SourceValidationError(f"{name} stderr hash mismatch")
    if value["classification"] not in {"PASS", "FAIL", "INFRASTRUCTURE_INVALID"}:
        raise SourceValidationError(f"{name} classification invalid")


def validate_source_entry(value: Mapping[str, Any], *, confirmatory: bool) -> None:
    if set(value) != SOURCE_ENTRY_REQUIRED_FIELDS:
        missing = sorted(SOURCE_ENTRY_REQUIRED_FIELDS - set(value))
        extra = sorted(set(value) - SOURCE_ENTRY_REQUIRED_FIELDS)
        raise SourceValidationError(
            f"source entry schema mismatch: missing={missing}; extra={extra}"
        )
    if not re.fullmatch(r"src-[a-z0-9][a-z0-9-]+", str(value["source_id"])):
        raise SourceValidationError("invalid source ID")
    tiers = value["source_tier_by_target"]
    if not isinstance(tiers, dict) or set(tiers) != set(DEVELOPMENT_IDS):
        raise SourceValidationError("source tiers must cover the exact development set")
    if any(tier not in {"S1", "S2", "S3"} for tier in tiers.values()):
        raise SourceValidationError("invalid source tier")
    if not _SHA1.fullmatch(str(value["repository_commit"])):
        raise SourceValidationError("invalid source commit")
    if value["language"] != "python":
        raise SourceValidationError("source language is outside the frozen universe")
    if not isinstance(value["source_task_description"], str) or not value[
        "source_task_description"
    ].strip():
        raise SourceValidationError("source task description is empty")
    provenance = value["source_task_provenance"]
    if not isinstance(provenance, dict) or provenance.get("kind") not in {
        "UPSTREAM_TEST",
        "COMMIT_MESSAGE",
        "IMMUTABLY_CAPTURED_ISSUE_OR_PR",
        "VERSION_PINNED_DOCUMENTATION",
    }:
        raise SourceValidationError("source task provenance is not permitted")
    if not isinstance(value["source_implementation_or_patch"], str) or not value[
        "source_implementation_or_patch"
    ].strip():
        raise SourceValidationError("source implementation is empty")
    _validate_command_evidence(value["source_build"], "source_build")
    _validate_command_evidence(value["source_task_test"], "source_task_test")
    if value["source_test_result"] != value["source_task_test"]["classification"]:
        raise SourceValidationError("source test result disagrees with evidence")
    if confirmatory and (
        value["source_build"]["classification"] != "PASS"
        or value["source_task_test"]["classification"] != "PASS"
    ):
        raise SourceValidationError("confirmatory source build/task test did not pass")
    validate_focal_safety(value["focal_source_safety"], confirmatory=confirmatory)
    if stable_record_hash(value["environment"]) != value["source_environment_hash"]:
        raise SourceValidationError("source environment hash mismatch")
    hashes = value["source_artifact_hashes"]
    if not isinstance(hashes, dict) or any(
        not _SHA256.fullmatch(str(digest)) for digest in hashes.values()
    ):
        raise SourceValidationError("source artifact hashes are invalid")
    availability = value["available_before_target_B"]
    if not isinstance(availability, dict) or set(availability) != set(DEVELOPMENT_IDS) or any(
        not isinstance(flag, bool) for flag in availability.values()
    ):
        raise SourceValidationError("target-relative source availability is invalid")
    reconstruction = value["reconstruction"]
    if not isinstance(reconstruction, dict) or not {
        "fetch_command",
        "checkout_command",
        "tree_sha256",
        "git_tree_object_sha1",
    } <= set(reconstruction):
        raise SourceValidationError("source reconstruction evidence is incomplete")
    if not _SHA256.fullmatch(str(reconstruction["tree_sha256"])):
        raise SourceValidationError("source reconstruction tree hash is invalid")
    if not _SHA1.fullmatch(str(reconstruction["git_tree_object_sha1"])):
        raise SourceValidationError("source reconstruction Git tree is invalid")


def source_tree_evidence(materialization: Path) -> dict[str, Any]:
    root = Path(materialization).resolve(strict=True)
    return {
        "tree_sha256": tree_sha256(root),
        "file_count": sum(1 for path in root.rglob("*") if path.is_file()),
    }


def file_hash(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass(frozen=True)
class SealedPairLocator:
    sealed_root: Path

    def resolve_development_target(self, target_id: str) -> Path:
        from cmpilot.susvibes_feasibility import DEVELOPMENT_IDS

        if target_id not in DEVELOPMENT_IDS:
            raise PermissionError("sealed target is not in the development set")
        root = Path(self.sealed_root).resolve(strict=True)
        unresolved = root / target_id
        if unresolved.is_symlink():
            raise PermissionError("sealed target must be a real directory")
        candidate = unresolved.resolve(strict=True)
        try:
            candidate.relative_to(root)
        except ValueError as error:
            raise PermissionError("sealed target path escaped root") from error
        if not candidate.is_dir():
            raise PermissionError("sealed target must be a real directory")
        return candidate


def corpus_manifest_hash(entries: Sequence[Mapping[str, Any]]) -> str:
    ordered = sorted(entries, key=lambda entry: str(entry["source_id"]))
    return sha256_bytes(canonical_json(ordered))
