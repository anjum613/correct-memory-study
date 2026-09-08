#!/usr/bin/env python3
"""Durable-state Track A production reconciler, version 0.2.

The frozen v0.1 runner remains beside this file as historical evidence and as
the implementation of the already-frozen reviewer validators/capsule.  This
version replaces its orchestration semantics: repository state, not model
text or role exit status, selects every transition.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from typing import Any, Mapping, Sequence
import uuid

import review_sandbox_network as review_network


RUNNER_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(RUNNER_ROOT))
import track_a_runner as legacy  # noqa: E402


DEFAULT_WORKTREE = legacy.DEFAULT_WORKTREE
DEFAULT_RUNNER_ROOT = legacy.DEFAULT_RUNNER_ROOT
EXPECTED_BRANCH = legacy.EXPECTED_BRANCH
RUN_RELATIVE_PATH = legacy.RUN_RELATIVE_PATH
RUN_ID = "09fafb41e8c4c29e4774ff9cc98027ed0630c2f4422ac801ea19bf19fdd24879"
NEW_AMENDMENT_RELATIVE_PATH = PurePosixPath(
    "benchmark-selection/screening/operational-amendments/"
    "durable-autonomous-orchestration-v0.1"
)
NEW_AMENDMENT_ID = "candidate-screening-v0.2.0-durable-autonomous-orchestration-v0.1"
LIFECYCLE_CORRECTION_RELATIVE_PATH = PurePosixPath(
    "benchmark-selection/screening/operational-amendments/"
    "autonomous-runner-lifecycle-correction-v0.1"
)
LIFECYCLE_CORRECTION_ID = (
    "candidate-screening-v0.2.0-autonomous-runner-lifecycle-correction-v0.1"
)
ENGINEERING_CORRECTION_RELATIVE_PATH = PurePosixPath(
    "benchmark-selection/screening/operational-amendments/"
    "autonomous-runner-preproduction-integrity-correction-v0.1"
)
ENGINEERING_CORRECTION_ID = (
    "candidate-screening-v0.2.0-autonomous-runner-preproduction-integrity-"
    "correction-v0.1"
)
NETWORK_CORRECTION_RELATIVE_PATH = PurePosixPath(
    "benchmark-selection/screening/operational-amendments/"
    "autonomous-runner-network-recovery-correction-v0.1"
)
NETWORK_CORRECTION_ID = (
    "candidate-screening-v0.2.0-autonomous-runner-network-recovery-"
    "correction-v0.1"
)
STRUCTURED_OUTPUT_CORRECTION_RELATIVE_PATH = PurePosixPath(
    "benchmark-selection/screening/operational-amendments/"
    "autonomous-ai-review-structured-output-correction-v0.1"
)
STRUCTURED_OUTPUT_CORRECTION_ID = (
    "candidate-screening-v0.2.0-autonomous-ai-review-structured-output-"
    "correction-v0.1"
)
EVIDENCE_REFERENCE_CORRECTION_RELATIVE_PATH = PurePosixPath(
    "benchmark-selection/screening/operational-amendments/"
    "autonomous-ai-review-evidence-reference-correction-v0.1"
)
EVIDENCE_REFERENCE_CORRECTION_ID = (
    "candidate-screening-v0.2.0-autonomous-ai-review-evidence-reference-"
    "correction-v0.1"
)
CANONICAL_RECONCILIATION_CORRECTION_RELATIVE_PATH = PurePosixPath(
    "benchmark-selection/screening/operational-amendments/"
    "autonomous-ai-review-canonical-reconciliation-correction-v0.1"
)
CANONICAL_RECONCILIATION_CORRECTION_ID = (
    "candidate-screening-v0.2.0-autonomous-ai-review-canonical-"
    "reconciliation-correction-v0.1"
)
TOPOLOGY_CORRECTION_RELATIVE_PATH = PurePosixPath(
    "benchmark-selection/screening/operational-amendments/"
    "position-materialization-topology-correction-v0.1"
)
TOPOLOGY_CORRECTION_ID = (
    "candidate-screening-v0.2.0-position-materialization-topology-"
    "correction-v0.1"
)
MATRIX_PATH = RUNNER_ROOT / "transition-matrix-v0.2.json"
RECOVERY_REGISTRY_PATH = RUNNER_ROOT / "deterministic-recovery-registry-v0.1.json"
COVERAGE_PATH = RUNNER_ROOT / "transition-test-coverage-v0.1.json"
DISCOVERY_RECOVERY_PLAN_PATH = RUNNER_ROOT / "discovery-recovery-plan-v0.1.json"
MATERIALIZER_RELATIVE_PATH = PurePosixPath(
    "scripts/materialize_candidate_screening_position_v020_v03.py"
)
HEARTBEAT_INTERVAL_SECONDS = 30
HEARTBEAT_STALE_SECONDS = 90
MAX_ROLE_TRANSITIONS_PER_POSITION = 32
SAFE_RETRY_LIMIT = 1
NETWORK_WAIT_INTERVAL_SECONDS = 30
NETWORK_WAIT_LIMIT_SECONDS = 15 * 60
CODEX_NETWORK_STALL_SECONDS = 10 * 60
MAX_NETWORK_STALL_RETRIES = 2
EXPECTED_CODEX_VERSION = "codex-cli 0.150.1"
FROZEN_CODEX_EXECUTABLE = Path("/home/anjum/.local/npm/bin/codex")
DISCOVERY_TRANSACTION_RELATIVE_PATH = PurePosixPath(
    "benchmark-selection/discovery/runs/v0.3/"
    "full-production-resume-20260819T033500Z-9bc403174"
)
EXPECTED_CODEX_OPTIONS = (
    "--json",
    "--ephemeral",
    "--ignore-user-config",
    "--color",
    "never",
    "--dangerously-bypass-approvals-and-sandbox",
    "--model",
    "gpt-5.6-sol",
    "--cd",
)
BLOCKER_SHA256 = "f69eab710bf1c9cda3a025e86f40f7fbe52de02e88d7a30aa711ff40a0cac9c8"
BLOCKER_SCHEMA = "candidate-screening-autonomous-blocker-v0.1"
BLOCKER_CLASS = "MISSING_FROZEN_INTERFACE"
BLOCKER_STAGE = "POSITION_AUTHORIZATION_AND_CANDIDATE_MANIFEST_MATERIALIZATION"
HEARTBEAT_SCHEMA = "track-a-runner-heartbeat-v0.2"
HEARTBEAT_NORMALIZATION_ID = "track-a-heartbeat-active-pid-normalization-v0.1"


class RunnerError(legacy.RunnerError):
    """A state the durable reconciler cannot prove safe."""


class ReviewSandboxNetworkUnavailable(RunnerError):
    """The exact reviewer sandbox could not establish bounded connectivity."""


class ProviderOutputSchemaIncompatible(RunnerError):
    """The reviewer Structured Output interface failed before child launch."""


class ProviderEvidenceReferenceContractIncompatible(RunnerError):
    """Assignment evidence vocabulary failed before reviewer child launch."""


NETWORK_TRANSPORT_PATTERNS = (
    "reconnecting... waiting for network",
    "failed to lookup address information",
    "error sending request",
    "falling back from websockets to https",
    "transport channel closed",
    "connection failed:",
)
INVALID_PROVIDER_SCHEMA_CODE = "invalid_json_schema"
INVALID_PROVIDER_SCHEMA_FAILURE = "CODEX_OUTPUT_SCHEMA_INVALID"


def is_invalid_provider_schema_failure(stdout: str, stderr: str) -> bool:
    """Recognize provider schema rejection without treating it as transport."""

    combined = f"{stdout}\n{stderr}"
    return (
        INVALID_PROVIDER_SCHEMA_CODE in combined
        and "text.format.schema" in combined
    )


def invalid_provider_schema_allows_retry() -> bool:
    """The deterministic interface defect is never a network/general retry."""

    return False


def evidence_reference_contract_allows_retry() -> bool:
    """Deterministic evidence-contract failures never use network retry."""

    return False


def canonical_decision_processing_allows_retry() -> bool:
    """Deterministic canonical-decision failures never use network retry."""

    return legacy.canonical_decision_processing_allows_retry()


def validate_provider_output_schema_for_role(
    worktree: Path, role: legacy.Role
) -> dict[str, str]:
    """Validate the exact provider schema/profile used by either reviewer."""

    if role not in {legacy.Role.AI_FIRST_REVIEW, legacy.Role.AI_SECOND_REVIEW}:
        raise RunnerError("provider output schema is only defined for AI reviewers")
    source_root = str(worktree / "src")
    inserted = source_root not in sys.path
    if inserted:
        sys.path.insert(0, source_root)
    try:
        from cmpilot.ai_review_provider_interface_v01 import (  # type: ignore
            validate_provider_schema_compatibility,
        )
        from cmpilot.ai_review_evidence_reference_interface_v01 import (  # type: ignore
            bind_provider_schema_to_allowed_refs,
        )

        correction = worktree / legacy.PROVIDER_CORRECTION_RELATIVE_PATH
        schema_path = correction / legacy.AI_PROVIDER_OUTPUT_SCHEMA
        profile_path = correction / legacy.AI_PROVIDER_COMPATIBILITY_PROFILE
        for path in (schema_path, profile_path):
            if path.is_symlink() or not path.is_file():
                raise RunnerError(f"provider interface artifact is absent: {path}")
        schema = read_json(schema_path)
        profile = read_json(profile_path)
        if not isinstance(schema, dict) or not isinstance(profile, dict):
            raise RunnerError("provider interface artifacts must be objects")
        validate_provider_schema_compatibility(schema, profile)
        contract_schema = bind_provider_schema_to_allowed_refs(
            schema, profile, ("synthetic-evidence-reference",)
        )
        return {
            "role": role.value,
            "schema_path": str(schema_path),
            "schema_sha256": sha256_bytes(
                legacy.canonical_json_bytes(contract_schema)
            ),
            "template_schema_sha256": sha256_file(schema_path),
            "profile_path": str(profile_path),
            "profile_sha256": sha256_file(profile_path),
            "capsule_schema_path": f"/workspace/{legacy.AI_OUTPUT_SCHEMA}",
        }
    except RunnerError:
        raise
    except Exception as error:
        raise RunnerError(f"provider output schema is incompatible: {error}") from error
    finally:
        if inserted:
            sys.path.remove(source_root)


def validate_synthetic_provider_projection(worktree: Path) -> dict[str, str]:
    """Run the candidate-free provider-to-canonical doctor fixture."""

    source_root = str(worktree / "src")
    inserted = source_root not in sys.path
    if inserted:
        sys.path.insert(0, source_root)
    try:
        from cmpilot.ai_review_evidence_reference_interface_v01 import (  # type: ignore
            build_assignment_bound_evidence_contract,
            project_assignment_bound_provider_to_canonical,
        )

        correction = worktree / legacy.PROVIDER_CORRECTION_RELATIVE_PATH
        schema = read_json(correction / legacy.AI_PROVIDER_OUTPUT_SCHEMA)
        profile = read_json(correction / legacy.AI_PROVIDER_COMPATIBILITY_PROFILE)
        fixture_path = correction / "synthetic-provider-output.json"
        fixture = read_json(fixture_path)
        if not all(isinstance(value, dict) for value in (schema, profile, fixture)):
            raise RunnerError("provider projection doctor artifacts must be objects")
        packet = SimpleNamespace(
            review_packet_sha256=fixture["review_packet_sha256"],
            candidate_result=SimpleNamespace(candidate_id=fixture["candidate_id"]),
            evidence_index=(
                SimpleNamespace(evidence_id="synthetic-evidence-1"),
            ),
        )
        assignment = {
            "reviewer_role": "AI_FIRST_REVIEW",
            "candidate_id": fixture["candidate_id"],
            "review_packet": {
                "path": "synthetic-review-packet.json",
                "review_packet_sha256": fixture["review_packet_sha256"],
            },
        }
        contract = build_assignment_bound_evidence_contract(
            schema, profile, assignment, lambda path: packet
        )
        projection = project_assignment_bound_provider_to_canonical(
            fixture, contract, profile
        )
        return {
            "fixture_sha256": sha256_file(fixture_path),
            "provider_schema_sha256": contract.provider_schema_sha256,
            "projection_sha256": projection.semantic_projection_sha256,
            "canonical_decision_sha256": projection.sealed_canonical_decision[
                "review_decision_sha256"
            ],
        }
    except RunnerError:
        raise
    except Exception as error:
        raise RunnerError(f"provider projection failed: {error}") from error
    finally:
        if inserted:
            sys.path.remove(source_root)


def validate_assignment_evidence_contract(
    repository: "ProductionRepositoryV2",
    role: legacy.Role,
    assignment_path: Path,
) -> dict[str, Any]:
    """Validate the actual role assignment before any reviewer process launch."""

    assignment = repository.validate_assignment(assignment_path, role)
    contract, _, _ = repository.assignment_bound_evidence_contract(assignment)
    if contract.reviewer_role != role.value:
        raise RunnerError("assignment-bound evidence contract role differs")
    return {
        "role": role.value,
        "assignment_path": str(assignment_path),
        "allowed_evidence_refs": list(contract.allowed_evidence_refs),
        "provider_schema_sha256": contract.provider_schema_sha256,
        "canonical_order_source": contract.canonical_order_source,
    }


def validate_synthetic_assignment_contract(
    worktree: Path, role: legacy.Role
) -> dict[str, Any]:
    """Exercise one role's contract without any production reviewer material."""

    if role not in {legacy.Role.AI_FIRST_REVIEW, legacy.Role.AI_SECOND_REVIEW}:
        raise RunnerError("synthetic evidence contract role is invalid")

    source_root = str(worktree / "src")
    inserted = source_root not in sys.path
    if inserted:
        sys.path.insert(0, source_root)
    try:
        from cmpilot.ai_review_evidence_reference_interface_v01 import (  # type: ignore
            build_assignment_bound_evidence_contract,
        )

        correction = worktree / legacy.PROVIDER_CORRECTION_RELATIVE_PATH
        schema = read_json(correction / legacy.AI_PROVIDER_OUTPUT_SCHEMA)
        profile = read_json(correction / legacy.AI_PROVIDER_COMPATIBILITY_PROFILE)
        if not isinstance(schema, dict) or not isinstance(profile, dict):
            raise RunnerError("provider interface artifacts must be objects")
        suffix = "a" if role is legacy.Role.AI_FIRST_REVIEW else "b"
        candidate_id = f"SYNTHETIC-BLINDED-{suffix.upper()}"
        evidence_id = f"synthetic-blinded-{suffix}-evidence"
        packet = SimpleNamespace(
            review_packet_sha256=suffix * 64,
            candidate_result=SimpleNamespace(candidate_id=candidate_id),
            evidence_index=(
                SimpleNamespace(evidence_id=evidence_id),
            ),
        )
        assignment = {
            "reviewer_role": role.value,
            "candidate_id": candidate_id,
            "review_packet": {
                "path": f"synthetic-blinded-{suffix}-review-packet.json",
                "review_packet_sha256": suffix * 64,
            },
            "prohibited_information_boundary": {
                "ai_reviewer_a_vector": True,
                "ai_reviewer_a_outcome": True,
                "ai_reviewer_a_focal_hypothesis": True,
            },
        }
        loaded: list[str] = []

        def load_packet(path: str) -> Any:
            loaded.append(path)
            return packet

        contract = build_assignment_bound_evidence_contract(
            schema, profile, assignment, load_packet
        )
        if loaded != [f"synthetic-blinded-{suffix}-review-packet.json"]:
            raise RunnerError("synthetic reviewer contract read outside its assignment")
        return {
            "role": contract.reviewer_role,
            "allowed_evidence_refs": list(contract.allowed_evidence_refs),
            "provider_schema_sha256": contract.provider_schema_sha256,
            "ai_a_material_loaded": False,
        }
    except RunnerError:
        raise
    except Exception as error:
        raise RunnerError(
            f"synthetic blinded reviewer contract failed: {error}"
        ) from error
    finally:
        if inserted:
            sys.path.remove(source_root)


def validate_doctor_evidence_contract(
    repository: Any, worktree: Path, role: legacy.Role
) -> dict[str, Any]:
    """Use an available due assignment, otherwise a candidate-free fixture."""

    if isinstance(repository, ProductionRepositoryV2):
        position = repository._snapshot_at_actual_head().next_due_position
        if role is legacy.Role.AI_FIRST_REVIEW:
            assignment_path = (
                repository.position_path(position) / "ai-reviewer-a-assignment.json"
            )
        else:
            assignment_path = repository.latest_b_assignment(position)
        if assignment_path is not None and assignment_path.is_file():
            return validate_assignment_evidence_contract(
                repository, role, assignment_path
            )
    return validate_synthetic_assignment_contract(worktree, role)


class NetworkStallDetector:
    """Detect continuous network-only output without imposing a total timeout."""

    def __init__(self, started: float, threshold_seconds: float) -> None:
        self.threshold_seconds = threshold_seconds
        self.last_substantive_progress = started
        self.network_failure_since: float | None = None

    def observe(self, text: str, now: float) -> None:
        for line in text.splitlines():
            normalized = line.strip().lower()
            if not normalized:
                continue
            if any(pattern in normalized for pattern in NETWORK_TRANSPORT_PATTERNS):
                if self.network_failure_since is None:
                    self.network_failure_since = now
                continue
            self.last_substantive_progress = now
            self.network_failure_since = None

    def stalled(self, now: float) -> bool:
        return (
            self.network_failure_since is not None
            and now - self.network_failure_since >= self.threshold_seconds
            and now - self.last_substantive_progress >= self.threshold_seconds
        )


def _read_output_delta(path: Path, offset: int) -> tuple[str, int]:
    try:
        with path.open("rb") as stream:
            stream.seek(offset)
            body = stream.read()
            return body.decode("utf-8", errors="replace"), stream.tell()
    except OSError:
        return "", offset


def _terminate_process_group(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
        process.wait()


class DurableState(StrEnum):
    PRE_POSITION = "PRE_POSITION"
    ADMINISTRATIVE_TERMINAL = "ADMINISTRATIVE_TERMINAL"
    POSITION_MATERIALIZATION_REQUIRED = "POSITION_MATERIALIZATION_REQUIRED"
    POSITION_MATERIALIZED = "POSITION_MATERIALIZED"
    TPTM_REQUIRED = "TPTM_REQUIRED"
    AUTO_MECHANICAL_TERMINAL = "AUTO_MECHANICAL_TERMINAL"
    OUT_OF_SCOPE_TERMINAL = "OUT_OF_SCOPE_TERMINAL"
    STRUCTURED_REVIEW_REQUIRED = "STRUCTURED_REVIEW_REQUIRED"
    AI_FIRST_ASSIGNMENT_READY = "AI_FIRST_ASSIGNMENT_READY"
    AI_FIRST_REVIEW_REQUIRED = "AI_FIRST_REVIEW_REQUIRED"
    AI_FIRST_DECISION_READY = "AI_FIRST_DECISION_READY"
    CONTINUATION_AFTER_A = "CONTINUATION_AFTER_A"
    AI_SECOND_NOT_REQUIRED = "AI_SECOND_NOT_REQUIRED"
    AI_SECOND_ASSIGNMENT_REQUIRED = "AI_SECOND_ASSIGNMENT_REQUIRED"
    AI_SECOND_ASSIGNMENT_CORRECTION_REQUIRED = (
        "AI_SECOND_ASSIGNMENT_CORRECTION_REQUIRED"
    )
    AI_SECOND_REVIEW_REQUIRED = "AI_SECOND_REVIEW_REQUIRED"
    AI_SECOND_DECISION_READY = "AI_SECOND_DECISION_READY"
    COMBINATION_REQUIRED = "COMBINATION_REQUIRED"
    REVIEW_REJECT = "REVIEW_REJECT"
    REVIEW_RETAIN = "REVIEW_RETAIN"
    REVIEW_UNRESOLVED = "REVIEW_UNRESOLVED"
    CONSTRAINED_FAMILY_FEASIBILITY_REQUIRED = (
        "CONSTRAINED_FAMILY_FEASIBILITY_REQUIRED"
    )
    NO_UNIQUE_FOCAL_FAILURE = "NO_UNIQUE_FOCAL_FAILURE"
    CONSTRUCTION_REQUIRED = "CONSTRUCTION_REQUIRED"
    CONSTRUCTION_FAILED = "CONSTRUCTION_FAILED"
    FAMILY_READY = "FAMILY_READY"
    EXECUTABLE_VALIDATION_REQUIRED = "EXECUTABLE_VALIDATION_REQUIRED"
    EXECUTABLE_VALIDATION_FAILED = "EXECUTABLE_VALIDATION_FAILED"
    FINAL_READY = "FINAL_READY"
    TERMINAL_PUBLICATION_PENDING = "TERMINAL_PUBLICATION_PENDING"
    TERMINAL_PUBLISHED = "TERMINAL_PUBLISHED"
    GLOBAL_STOP = "GLOBAL_STOP"
    DISCOVERY_ARTIFACT_PROVISIONING_REQUIRED = (
        "DISCOVERY_ARTIFACT_PROVISIONING_REQUIRED"
    )
    REVIEWER_B_ASSIGNMENT_COMPLETION_REQUIRED = (
        "REVIEWER_B_ASSIGNMENT_COMPLETION_REQUIRED"
    )
    VALID_DESCENDANT_HEAD_RECONCILIATION = (
        "VALID_DESCENDANT_HEAD_RECONCILIATION"
    )
    DETERMINISTIC_INTERFACE_CORRECTION_REQUIRED = (
        "DETERMINISTIC_INTERFACE_CORRECTION_REQUIRED"
    )
    POST_ROLE_RECONCILIATION_REQUIRED = "POST_ROLE_RECONCILIATION_REQUIRED"
    PARTIAL_PUBLICATION_RECONCILIATION = "PARTIAL_PUBLICATION_RECONCILIATION"


class EventType(StrEnum):
    ROLE_COMPLETED = "ROLE_COMPLETED"
    DURABLE_STATE_CLASSIFIED = "DURABLE_STATE_CLASSIFIED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    AI_REVIEW_A = "AI_REVIEW_A"
    AI_REVIEW_B = "AI_REVIEW_B"
    COMBINATION_CONTINUATION = "COMBINATION_CONTINUATION"
    AUTO_CONTINUE = "AUTO_CONTINUE"
    BLOCKER = "BLOCKER"
    GLOBAL_STOP = "GLOBAL_STOP"
    MAX_POSITION_STOP = "MAX_POSITION_STOP"
    ERROR = "ERROR"
    DRY_RUN = "DRY_RUN"
    PRE_RUN_BLOCKER = "PRE_RUN_BLOCKER"
    NETWORK_PREFLIGHT = "NETWORK_PREFLIGHT"
    NETWORK_WAIT = "NETWORK_WAIT"
    CODEX_NETWORK_STALL = "CODEX_NETWORK_STALL"


@dataclass(frozen=True, slots=True)
class Classification:
    state: DurableState
    reason: str
    next_role: legacy.Role | None
    recovery_id: str | None = None


@dataclass(frozen=True, slots=True)
class RunnerOutcome:
    event: EventType
    positions_completed: int
    next_due_position: int
    reason: str


@dataclass(frozen=True, slots=True)
class LockObservation:
    status: str
    owner_pids: tuple[int, ...] = ()
    owner_lookup_available: bool = True


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return legacy.read_json(path)


def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    legacy.atomic_replace_json(path, value)


def append_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = legacy.canonical_json_bytes(value) + b"\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(descriptor, body)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def process_alive(pid: int | None) -> bool:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _codex_diagnostic(
    attempted: Path,
    *,
    exists: bool,
    executable: bool,
    version_check_status: str,
    os_error: str,
    regular: bool = False,
) -> str:
    return (
        f"attempted_executable_path={attempted} exists={str(exists).lower()} "
        f"regular={str(regular).lower()} executable={str(executable).lower()} "
        f"version_check_status={version_check_status} exact_os_error={os_error}"
    )


def resolve_canonical_codex_executable(codex_bin: Path | None = None) -> Path:
    """Resolve the one frozen Codex path without consulting PATH."""

    attempted = codex_bin or FROZEN_CODEX_EXECUTABLE
    if not attempted.is_absolute():
        raise RunnerError(
            _codex_diagnostic(
                attempted,
                exists=False,
                executable=False,
                version_check_status="NOT_RUN",
                os_error="PATH_NOT_ABSOLUTE",
            )
        )
    try:
        authority = FROZEN_CODEX_EXECUTABLE.resolve(strict=True)
    except OSError as error:
        raise RunnerError(
            _codex_diagnostic(
                FROZEN_CODEX_EXECUTABLE,
                exists=FROZEN_CODEX_EXECUTABLE.exists(),
                executable=False,
                version_check_status="NOT_RUN",
                os_error=f"{type(error).__name__}: {error}",
            )
        ) from error
    try:
        canonical = attempted.resolve(strict=True)
        status = canonical.stat()
    except OSError as error:
        raise RunnerError(
            _codex_diagnostic(
                attempted,
                exists=attempted.exists(),
                executable=False,
                version_check_status="NOT_RUN",
                os_error=f"{type(error).__name__}: {error}",
            )
        ) from error
    regular = stat.S_ISREG(status.st_mode)
    executable = regular and os.access(canonical, os.X_OK)
    if canonical != authority:
        raise RunnerError(
            _codex_diagnostic(
                attempted,
                exists=True,
                regular=regular,
                executable=executable,
                version_check_status="NOT_RUN",
                os_error=f"FROZEN_PATH_MISMATCH: expected={authority}; observed={canonical}",
            )
        )
    if not executable:
        raise RunnerError(
            _codex_diagnostic(
                attempted,
                exists=True,
                regular=regular,
                executable=False,
                version_check_status="NOT_RUN",
                os_error="NOT_A_REGULAR_EXECUTABLE",
            )
        )
    return canonical


def verify_codex_cli(codex_bin: Path | None, cwd: Path) -> dict[str, str]:
    canonical = resolve_canonical_codex_executable(codex_bin)
    try:
        version = legacy.subprocess_text([str(canonical), "--version"], cwd=cwd).strip()
    except (OSError, legacy.RunnerError) as error:
        raise RunnerError(
            _codex_diagnostic(
                codex_bin or FROZEN_CODEX_EXECUTABLE,
                exists=True,
                regular=True,
                executable=True,
                version_check_status="ERROR",
                os_error=f"{type(error).__name__}: {error}",
            )
        ) from error
    if version != EXPECTED_CODEX_VERSION:
        raise RunnerError(
            _codex_diagnostic(
                codex_bin or FROZEN_CODEX_EXECUTABLE,
                exists=True,
                regular=True,
                executable=True,
                version_check_status=(
                    f"FAIL(expected={EXPECTED_CODEX_VERSION},observed={version})"
                ),
                os_error="NONE",
            )
        )
    try:
        help_text = legacy.subprocess_text([str(canonical), "exec", "--help"], cwd=cwd)
    except (OSError, legacy.RunnerError) as error:
        raise RunnerError(
            _codex_diagnostic(
                codex_bin or FROZEN_CODEX_EXECUTABLE,
                exists=True,
                regular=True,
                executable=True,
                version_check_status="PASS",
                os_error=f"{type(error).__name__}: {error}",
            )
        ) from error
    required = {
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--color",
        "--dangerously-bypass-approvals-and-sandbox",
        "--model",
        "--cd",
        "--output-schema",
        "--output-last-message",
    }
    missing = sorted(option for option in required if option not in help_text)
    if missing:
        raise RunnerError(f"Codex exec interface options are absent: {','.join(missing)}")
    return {
        "path": str(canonical),
        "configured_path": str(FROZEN_CODEX_EXECUTABLE),
        "version": version,
        "interface": "codex exec --help",
        "status": "PASS",
    }


class Heartbeat:
    def __init__(self, root: Path, runner_id: str) -> None:
        self.path = root / "state" / "heartbeat.json"
        self.runner_id = runner_id
        self.runner_pid: int | None = os.getpid()
        self.last_runner_pid: int | None = self.runner_pid
        self.child_pid: int | None = None
        self.last_child_pid: int | None = None
        self.current_position: int | None = None
        self.current_role: str | None = None
        self.child_started_at_utc: str | None = None
        self.last_child_started_at_utc: str | None = None
        self.production_head: str | None = None
        self.records_published: int | None = None
        self.next_due_position: int | None = None
        self.last_event = "RUNNER_START"
        self.last_event_timestamp = utc_now()
        self.last_classification: str | None = None
        self.last_reason = "startup reconciliation pending"
        self.network_state = "NOT_APPLICABLE"
        self.network_wait_seconds = 0
        self.review_attempt = 0
        self.network_retry_count = 0
        self.network_failure_since: str | None = None
        self.network_retry_role: str | None = None
        self.network_retry_position: int | None = None
        previous_path = root / "state" / "heartbeat.json"
        if previous_path.is_file() and not previous_path.is_symlink():
            try:
                previous = read_json(previous_path)
            except (OSError, ValueError, RunnerError):
                previous = None
            if isinstance(previous, dict):
                previous_retry = previous.get("network_retry_count")
                previous_attempt = previous.get("review_attempt")
                if isinstance(previous_retry, int) and previous_retry >= 0:
                    self.network_retry_count = previous_retry
                if isinstance(previous_attempt, int) and previous_attempt >= 0:
                    self.review_attempt = previous_attempt
                if isinstance(previous.get("network_retry_role"), str):
                    self.network_retry_role = previous["network_retry_role"]
                if isinstance(previous.get("network_retry_position"), int):
                    self.network_retry_position = previous["network_retry_position"]
        self.role_started_monotonic: float | None = None
        self._last_write_monotonic = 0.0
        self._write_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"track-a-heartbeat-{self.runner_id}",
            daemon=True,
        )
        self._thread.start()

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.wait(1.0):
            self.reconcile_child_liveness()
            self.write(status="RUNNING")

    def reconcile_child_liveness(self) -> bool:
        if self.child_pid is None or process_alive(self.child_pid):
            return False
        self.last_child_pid = self.child_pid
        self.last_child_started_at_utc = self.child_started_at_utc
        self.child_pid = None
        self.child_started_at_utc = None
        self.last_reason = "active child exited; durable reconciliation pending"
        return True

    def update_snapshot(self, snapshot: legacy.Snapshot) -> None:
        self.production_head = snapshot.head
        self.records_published = snapshot.records_published
        self.next_due_position = snapshot.next_due_position
        self.current_position = snapshot.next_due_position

    def event(self, event: str, reason: str, classification: str | None = None) -> None:
        self.last_event = event
        self.last_event_timestamp = utc_now()
        self.last_reason = reason
        if classification is not None:
            self.last_classification = classification
        self.write(status="RUNNING", force=True)

    def set_role(self, role: str | None, child_pid: int | None = None) -> None:
        if role != self.current_role:
            self.role_started_monotonic = None if role is None else time.monotonic()
            self.child_started_at_utc = None if role is None else utc_now()
        self.current_role = role
        if child_pid is not None:
            self.last_child_pid = child_pid
            self.last_child_started_at_utc = self.child_started_at_utc
        self.child_pid = child_pid
        self.write(status="RUNNING", force=True)

    def set_network_state(
        self,
        state: str,
        *,
        wait_seconds: int = 0,
        failure_since: str | None = None,
        reason: str | None = None,
    ) -> None:
        self.network_state = state
        self.network_wait_seconds = max(0, wait_seconds)
        self.network_failure_since = failure_since
        if reason is not None:
            self.last_reason = reason
        self.write(status="RUNNING", force=True)

    def set_review_attempt(
        self,
        attempt: int,
        network_retry_count: int,
        *,
        role: str | None = None,
        position: int | None = None,
    ) -> None:
        if role is not None and position is not None:
            if (
                self.network_retry_role != role
                or self.network_retry_position != position
            ):
                self.review_attempt = 0
                self.network_retry_count = 0
            self.network_retry_role = role
            self.network_retry_position = position
        self.review_attempt = max(0, attempt)
        self.network_retry_count = max(0, network_retry_count)
        self.write(status="RUNNING", force=True)

    def network_fields(self) -> dict[str, Any]:
        return {
            "network_state": self.network_state,
            "network_wait_seconds": self.network_wait_seconds,
            "review_attempt": self.review_attempt,
            "network_retry_count": self.network_retry_count,
            "network_failure_since": self.network_failure_since,
            "network_retry_role": self.network_retry_role,
            "network_retry_position": self.network_retry_position,
        }

    def seconds_in_role(self) -> int:
        if self.role_started_monotonic is None:
            return 0
        return max(0, int(time.monotonic() - self.role_started_monotonic))

    def write(self, *, status: str, force: bool = False) -> None:
        if status not in {"RUNNING", "STOPPED"}:
            raise RunnerError(f"unknown heartbeat status: {status}")
        with self._write_lock:
            now = time.monotonic()
            if (
                not force
                and now - self._last_write_monotonic < HEARTBEAT_INTERVAL_SECONDS
            ):
                return
            atomic_json(
                self.path,
                {
                    "schema": HEARTBEAT_SCHEMA,
                    "status": status,
                    "runner_pid": self.runner_pid if status == "RUNNING" else None,
                    "child_pid": self.child_pid if status == "RUNNING" else None,
                    "last_runner_pid": self.last_runner_pid,
                    "last_child_pid": self.last_child_pid,
                    "child_started_at_utc": (
                        self.child_started_at_utc if status == "RUNNING" else None
                    ),
                    "last_child_started_at_utc": self.last_child_started_at_utc,
                    "runner_id": self.runner_id,
                    "position": self.current_position,
                    "role": self.current_role,
                    "current_position": self.current_position,
                    "current_role": self.current_role,
                    "production_head": self.production_head,
                    "records_published": self.records_published,
                    "next_due_position": self.next_due_position,
                    "last_event": self.last_event,
                    "last_event_timestamp": self.last_event_timestamp,
                    "heartbeat_timestamp": utc_now(),
                    "seconds_in_current_role": self.seconds_in_role(),
                    "last_classification": self.last_classification,
                    "last_reason": self.last_reason,
                    **self.network_fields(),
                },
            )
            self._last_write_monotonic = now

    def stopped(self, reason: str) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=2.0)
        self._thread = None
        if self.runner_pid is not None:
            self.last_runner_pid = self.runner_pid
        if self.child_pid is not None:
            self.last_child_pid = self.child_pid
            self.last_child_started_at_utc = self.child_started_at_utc
        self.runner_pid = None
        self.child_pid = None
        self.child_started_at_utc = None
        self.current_role = None
        self.role_started_monotonic = None
        self.last_reason = reason
        self.write(status="STOPPED", force=True)


class StructuredLogger:
    def __init__(self, root: Path, runner_id: str, heartbeat: Heartbeat) -> None:
        self.root = root
        self.runner_id = runner_id
        self.heartbeat = heartbeat
        self.run_dir = root / "logs" / runner_id
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.events_path = self.run_dir / "events.jsonl"
        atomic_json(
            root / "state" / "latest-run.json",
            {
                "schema": "track-a-latest-run-v0.1",
                "runner_id": runner_id,
                "log_dir": str(self.run_dir),
                "events_path": str(self.events_path),
            },
        )

    def emit_event(self, event_type: EventType, **fields: Any) -> None:
        reason = str(fields.get("reason", event_type.value))
        event = {
            "schema": "track-a-runner-event-v0.2",
            "runner_id": self.runner_id,
            "timestamp_utc": utc_now(),
            "event_type": event_type.value,
            **self.heartbeat.network_fields(),
            **fields,
        }
        append_jsonl(self.events_path, event)
        self.heartbeat.event(
            event_type.value,
            reason,
            str(fields["durable_state"]) if "durable_state" in fields else None,
        )

    def emit(self, classification: Any, **fields: Any) -> None:
        """Compatibility surface used only by the frozen executor metadata path."""

        value = classification.value if hasattr(classification, "value") else str(classification)
        mapping = {
            "AI_REVIEW_A": EventType.AI_REVIEW_A,
            "AI_REVIEW_B": EventType.AI_REVIEW_B,
            "COMBINATION_CONTINUATION": EventType.COMBINATION_CONTINUATION,
            "BLOCKER": EventType.BLOCKER,
            "ERROR": EventType.ERROR,
            "DRY_RUN": EventType.DRY_RUN,
        }
        self.emit_event(mapping.get(value, EventType.ROLE_COMPLETED), **fields)

    def role_attempt_dir(self, position: int, role: legacy.Role, attempt: int) -> Path:
        names = {
            legacy.Role.POSITION_CONTROLLER: "controller",
            legacy.Role.AI_FIRST_REVIEW: "reviewer-a",
            legacy.Role.CONTINUATION_CONTROLLER: "continuation",
            legacy.Role.AI_SECOND_REVIEW: "reviewer-b",
            legacy.Role.COMBINATION_CONTINUATION_CONTROLLER: "combination-continuation",
        }
        path = (
            self.run_dir
            / f"position-{position:08d}"
            / names[role]
            / f"attempt-{attempt:02d}"
        )
        path.mkdir(parents=True, exist_ok=False)
        return path


def _network_probe_detail(result: review_network.SandboxNetworkProbe) -> str:
    return (
        f"role={result.role}; resolver_mode={result.resolver_mode}; "
        f"resolver_target={result.resolver_target}; dns={result.dns_status}; "
        f"https={result.https_status}; reason={result.reason}"
    )


def wait_for_reviewer_network(
    *,
    role: legacy.Role,
    position: int,
    probe: Any,
    heartbeat: Heartbeat,
    logger: StructuredLogger,
    interval_seconds: float = NETWORK_WAIT_INTERVAL_SECONDS,
    limit_seconds: float = NETWORK_WAIT_LIMIT_SECONDS,
    clock: Any = time.monotonic,
    sleeper: Any = time.sleep,
    utc_source: Any = utc_now,
) -> review_network.SandboxNetworkProbe:
    """Wait for the exact sandbox network, bounded without starting Codex."""

    started = clock()
    failure_since: str | None = None
    while True:
        result = probe()
        elapsed = max(0, int(clock() - started))
        if result.passed:
            heartbeat.set_network_state(
                "CONNECTED",
                wait_seconds=elapsed,
                failure_since=None,
                reason="review sandbox network preflight passed",
            )
            logger.emit_event(
                EventType.NETWORK_PREFLIGHT,
                position=position,
                role=role.value,
                network_state="CONNECTED",
                network_wait_seconds=elapsed,
                resolver_mode=result.resolver_mode,
                resolver_target=result.resolver_target,
                dns_status=result.dns_status,
                https_status=result.https_status,
                reason="exact reviewer sandbox network preflight passed",
            )
            return result
        if failure_since is None:
            failure_since = utc_source()
        if not result.retryable:
            heartbeat.set_network_state(
                "BLOCKED",
                wait_seconds=elapsed,
                failure_since=failure_since,
                reason=result.reason,
            )
            raise ReviewSandboxNetworkUnavailable(
                "REVIEW_SANDBOX_CONFIGURATION_REJECTED: "
                + _network_probe_detail(result)
            )
        heartbeat.set_network_state(
            "WAITING",
            wait_seconds=elapsed,
            failure_since=failure_since,
            reason="review sandbox network unavailable; bounded wait active",
        )
        logger.emit_event(
            EventType.NETWORK_WAIT,
            position=position,
            role=role.value,
            network_state="WAITING",
            network_wait_seconds=elapsed,
            network_failure_since=failure_since,
            resolver_mode=result.resolver_mode,
            resolver_target=result.resolver_target,
            dns_status=result.dns_status,
            https_status=result.https_status,
            reason=result.reason,
        )
        remaining = limit_seconds - (clock() - started)
        if remaining <= 0:
            heartbeat.set_network_state(
                "UNAVAILABLE",
                wait_seconds=max(0, int(clock() - started)),
                failure_since=failure_since,
                reason="bounded reviewer sandbox network wait exhausted",
            )
            raise ReviewSandboxNetworkUnavailable(
                "REVIEW_SANDBOX_NETWORK_UNAVAILABLE: bounded wait exhausted; "
                + _network_probe_detail(result)
            )
        sleeper(min(interval_seconds, remaining))


def validate_transition_definitions() -> tuple[dict[str, Any], dict[str, Any]]:
    matrix = read_json(MATRIX_PATH)
    registry = read_json(RECOVERY_REGISTRY_PATH)
    if (
        not isinstance(matrix, dict)
        or matrix.get("schema") != "track-a-durable-transition-matrix-v0.2"
        or matrix.get("authority") != "VALIDATED_REPOSITORY_DURABLE_STATE"
        or matrix.get("codex_prose_authoritative") is not False
        or matrix.get("unknown_state_policy") != "FAIL_CLOSED_BLOCKER"
        or matrix.get("automatic_continuation_semantics")
        != (
            "A true state value permits automatic dispatch only to the listed "
            "deterministic recovery or fresh role; it never authorizes an "
            "AUTO_CONTINUE event."
        )
        or matrix.get("auto_continue_event_rule")
        != (
            "AUTO_CONTINUE is permitted only after TERMINAL_PUBLISHED validates "
            "the terminal record, unit ledger transition, complete replay, "
            "absence of current-position nonterminal state, and legitimate "
            "successor due position."
        )
    ):
        raise RunnerError("transition matrix identity differs")
    rows = matrix.get("states")
    required_row = {
        "state",
        "recognition",
        "required_files",
        "forbidden_conflicts",
        "ledger_relationship",
        "head_behavior",
        "permitted_next_role",
        "new_codex_invocation_required",
        "deterministic_recovery",
        "automatic_continuation",
        "fail_closed",
    }
    if (
        not isinstance(rows, list)
        or any(not isinstance(row, dict) or set(row) != required_row for row in rows)
        or {row["state"] for row in rows} != {state.value for state in DurableState}
        or len(rows) != len(DurableState)
    ):
        raise RunnerError("transition matrix does not exactly cover durable states")
    if not isinstance(registry, dict) or registry.get("schema") != (
        "track-a-deterministic-recovery-registry-v0.1"
    ):
        raise RunnerError("deterministic recovery registry identity differs")
    recoveries = registry.get("recoveries")
    expected_recoveries = {
        "CURRENT_POSITION_MATERIALIZATION",
        "FROZEN_DISCOVERY_ARTIFACT_PROVISIONING",
        "REVIEWER_B_ASSIGNMENT_COMPLETION",
        "INTERRUPTED_TERMINAL_PUBLICATION_RECONCILIATION",
        "VALID_DESCENDANT_HEAD_RECONCILIATION",
    }
    required_recovery = {
        "id",
        "trigger_state",
        "required_validated_inputs",
        "operation",
        "allowed_outputs",
        "scientific_invariants_unchanged",
        "success_state",
        "failure_state",
    }
    if (
        not isinstance(recoveries, list)
        or any(not isinstance(row, dict) or set(row) != required_recovery for row in recoveries)
        or {row["id"] for row in recoveries} != expected_recoveries
    ):
        raise RunnerError("deterministic recovery registry is incomplete")
    return matrix, registry


def validate_coverage_manifest() -> dict[str, Any]:
    value = read_json(COVERAGE_PATH)
    if (
        not isinstance(value, dict)
        or value.get("schema") != "track-a-transition-test-coverage-v0.1"
        or not isinstance(value.get("required_scenarios"), list)
        or not isinstance(value.get("state_coverage"), list)
    ):
        raise RunnerError("transition coverage manifest identity differs")
    scenarios = value["required_scenarios"]
    expected_ids = [f"T{index:02d}" for index in range(1, len(scenarios) + 1)]
    if (
        len(scenarios) != 67
        or [row.get("id") for row in scenarios if isinstance(row, dict)] != expected_ids
        or any(
            not isinstance(row, dict)
            or set(row) != {"id", "scenario", "test"}
            or not all(isinstance(row[key], str) and row[key] for key in row)
            for row in scenarios
        )
    ):
        raise RunnerError("required transition scenarios are incomplete")
    state_rows = value["state_coverage"]
    if (
        any(
            not isinstance(row, dict)
            or set(row) != {"state", "test"}
            or not isinstance(row["test"], str)
            or not row["test"]
            for row in state_rows
        )
        or {row["state"] for row in state_rows} != {state.value for state in DurableState}
        or len(state_rows) != len(DurableState)
    ):
        raise RunnerError("not every durable state has an explicit transition test")
    test_source = (RUNNER_ROOT / "tests/test_track_a_runner_v2.py").read_text(
        encoding="utf-8"
    )
    references = [row["test"] for row in scenarios] + [
        row["test"] for row in state_rows
    ]
    missing_tests = sorted(
        {
            reference.split("[", 1)[0]
            for reference in references
            if f"def {reference.split('[', 1)[0]}(" not in test_source
        }
    )
    if missing_tests:
        raise RunnerError(f"coverage references absent tests: {','.join(missing_tests)}")
    return value


def validate_runtime_interface_coverage(worktree: Path) -> dict[str, int]:
    matrix, registry = validate_transition_definitions()
    validate_coverage_manifest()
    recovery_ids = {row["id"] for row in registry["recoveries"]}
    for row in matrix["states"]:
        state = DurableState(row["state"])
        recovery = row["deterministic_recovery"]
        role = STATE_ROLE_HANDLERS[state]
        if recovery is not None and recovery not in recovery_ids:
            raise RunnerError(f"state {state.value} references an unknown recovery")
        if (
            role is None
            and recovery is None
            and state not in {DurableState.TERMINAL_PUBLISHED, DurableState.GLOBAL_STOP}
        ):
            raise RunnerError(f"state {state.value} has no reachable handler")
    required_files = (
        worktree / MATERIALIZER_RELATIVE_PATH,
        worktree / "scripts/provision_frozen_discovery_artifacts.py",
        worktree
        / NEW_AMENDMENT_RELATIVE_PATH
        / "family-executable-validation.schema.json",
        DISCOVERY_RECOVERY_PLAN_PATH,
    )
    missing = [str(path) for path in required_files if not path.is_file()]
    if missing:
        raise RunnerError(f"registered deterministic interface is absent: {missing[0]}")
    if RECOVERY_HANDLERS != recovery_ids:
        raise RunnerError("runtime recovery handlers and frozen registry differ")
    return {
        "state_count": len(matrix["states"]),
        "recovery_count": len(registry["recoveries"]),
        "scenario_count": len(read_json(COVERAGE_PATH)["required_scenarios"]),
    }


def _frozen_discovery_recovery_rows() -> list[dict[str, Any]]:
    plan = read_json(DISCOVERY_RECOVERY_PLAN_PATH)
    plan_keys = {
        "schema",
        "classification",
        "candidate_content_parsed",
        "network_accessed",
        "records",
        "scientific_methodology_changed",
    }
    row_keys = {
        "id",
        "source_checkout",
        "transaction_relative_path",
        "expected_tree_sha256",
        "expected_file_count",
        "expected_total_bytes",
        "evidence_record_relative_path",
        "evidence_record_sha256",
    }
    if (
        not isinstance(plan, dict)
        or set(plan) != plan_keys
        or plan.get("schema") != "track-a-frozen-discovery-recovery-plan-v0.1"
        or plan.get("classification")
        != "HASH_VERIFIED_COPY_ONLY_CANONICAL_DISCOVERY_PROVISIONING"
        or plan.get("candidate_content_parsed") is not False
        or plan.get("network_accessed") is not False
        or plan.get("scientific_methodology_changed") is not False
        or not isinstance(plan.get("records"), list)
        or len(plan["records"]) != 2
    ):
        raise RunnerError("frozen discovery recovery plan identity differs")
    rows: list[dict[str, Any]] = []
    for row in plan["records"]:
        if not isinstance(row, dict) or set(row) != row_keys:
            raise RunnerError("discovery recovery plan row is invalid")
        rows.append(row)
    if {row["id"] for row in rows} != {"FAILED_PARENT", "SUCCESSFUL_RESUME"}:
        raise RunnerError("discovery recovery plan transaction set differs")
    return rows


def verify_frozen_discovery_transaction_inputs(
    repository: "ProductionRepositoryV2", transaction: PurePosixPath
) -> dict[str, Any]:
    matches = [
        row
        for row in _frozen_discovery_recovery_rows()
        if row["transaction_relative_path"] == str(transaction)
    ]
    if len(matches) != 1:
        raise RunnerError(
            f"frozen discovery transaction resolution is not unique: {transaction}"
        )
    row = matches[0]
    source_checkout = Path(row["source_checkout"])
    evidence_relative = PurePosixPath(row["evidence_record_relative_path"])
    if (
        not source_checkout.is_absolute()
        or transaction.is_absolute()
        or ".." in transaction.parts
        or evidence_relative.is_absolute()
        or ".." in evidence_relative.parts
    ):
        raise RunnerError("discovery recovery plan path escapes its authority")
    source = source_checkout / transaction
    destination = repository.worktree / transaction
    evidence = repository.worktree / evidence_relative
    if not evidence.is_file() or sha256_file(evidence) != row["evidence_record_sha256"]:
        raise RunnerError(f"frozen discovery provenance mismatch: artifact={evidence}")
    evidence_value = read_json(evidence)
    if (
        not isinstance(evidence_value, dict)
        or evidence_value.get("source_checkout") != str(source_checkout)
        or evidence_value.get("source_transaction_logical_path") != str(transaction)
        or evidence_value.get("destination_transaction_logical_path") != str(transaction)
        or evidence_value.get("source_tree_sha256") != row["expected_tree_sha256"]
        or evidence_value.get("destination_tree_sha256") != row["expected_tree_sha256"]
        or evidence_value.get("file_count") != row["expected_file_count"]
        or evidence_value.get("total_bytes") != row["expected_total_bytes"]
        or evidence_value.get("candidate_content_parsed") is not False
        or evidence_value.get("network_accessed") is not False
        or evidence_value.get("verification_status") != "PASS"
    ):
        raise RunnerError("frozen discovery provisioning evidence semantics differ")
    if not source.is_dir() or not destination.is_dir():
        missing = source if not source.is_dir() else destination
        raise RunnerError(f"frozen discovery transaction is absent: artifact={missing}")
    command = [
        sys.executable,
        str(repository.worktree / "scripts/provision_frozen_discovery_artifacts.py"),
        "verify",
        "--source",
        str(source),
        "--destination",
        str(destination),
    ]
    completed = subprocess.run(
        command,
        cwd=repository.worktree,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        env=legacy.sanitized_environment(),
    )
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RunnerError(
            "frozen discovery verifier output invalid: "
            + (completed.stderr.strip() or completed.stdout.strip())
        ) from error
    if (
        completed.returncode != 0
        or result.get("pass") is not True
        or result.get("source_tree_sha256") != row["expected_tree_sha256"]
        or result.get("destination_tree_sha256") != row["expected_tree_sha256"]
        or result.get("file_count") != row["expected_file_count"]
        or result.get("total_bytes") != row["expected_total_bytes"]
        or result.get("hardlink_independent") is not True
        or result.get("symlinks_present") is not False
        or result.get("network_accessed") is not False
    ):
        raise RunnerError(
            "frozen discovery transaction verification failed: "
            f"artifact={destination} expected_sha256={row['expected_tree_sha256']} "
            f"actual_sha256={result.get('destination_tree_sha256', 'UNAVAILABLE')} "
            "identity_type=TREE_SHA256"
        )
    return {
        "transaction": str(transaction),
        "source": str(source),
        "destination": str(destination),
        "tree_sha256": row["expected_tree_sha256"],
        "file_count": row["expected_file_count"],
        "total_bytes": row["expected_total_bytes"],
    }


def run_current_materialization_preflight(
    repository: "ProductionRepositoryV2", position: int
) -> dict[str, Any]:
    before = repository.durable_token(position)
    command = [
        sys.executable,
        str(repository.worktree / MATERIALIZER_RELATIVE_PATH),
        "--repository-root",
        str(repository.worktree),
        "--expected-position",
        str(position),
        "--preflight",
    ]
    completed = subprocess.run(
        command,
        cwd=repository.worktree,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        env=legacy.sanitized_environment(),
    )
    after = repository.durable_token(position)
    if before != after:
        raise RunnerError("materialization preflight changed durable production state")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RunnerError(
            "materialization preflight output invalid: "
            + (completed.stderr.strip() or completed.stdout.strip())
        ) from error
    if completed.returncode != 0 or result.get("pass") is not True:
        detail_fields = [
            f"error_code={result.get('error_code', 'UNKNOWN')}",
            f"artifact={result.get('artifact', result.get('error', 'UNAVAILABLE'))}",
            f"expected_sha256={result.get('expected_sha256', 'UNAVAILABLE')}",
            f"actual_sha256={result.get('actual_sha256', 'UNAVAILABLE')}",
        ]
        raise RunnerError(" ".join(detail_fields))
    discovery = verify_frozen_discovery_transaction_inputs(
        repository, DISCOVERY_TRANSACTION_RELATIVE_PATH
    )
    return {
        **result,
        "tree_sha256": discovery["tree_sha256"],
        "file_count": discovery["file_count"],
        "total_bytes": discovery["total_bytes"],
    }


def validate_reachable_recovery_inputs(
    repository: "ProductionRepositoryV2", classification: Classification, position: int
) -> dict[str, Any]:
    if classification.recovery_id == "CURRENT_POSITION_MATERIALIZATION":
        return run_current_materialization_preflight(repository, position)
    if classification.recovery_id == "FROZEN_DISCOVERY_ARTIFACT_PROVISIONING":
        rows = _frozen_discovery_recovery_rows()
        if any(not (Path(row["source_checkout"]) / row["transaction_relative_path"]).is_dir() for row in rows):
            raise RunnerError("a frozen discovery provisioning source transaction is absent")
        return {"check": "FROZEN_DISCOVERY_ARTIFACT_PROVISIONING_INPUTS"}
    return {
        "check": "CURRENT_REACHABLE_RECOVERY_INPUTS",
        "recovery_id": classification.recovery_id,
        "validation": "STATE_CLASSIFIER_INPUTS_ALREADY_VALIDATED",
    }


class ProductionRepositoryV2(legacy.ProductionRepository):
    """Authoritative repository reader with restart reconciliation."""

    def __init__(
        self,
        worktree: Path,
        runner_root: Path,
        state_path: Path,
        logger: StructuredLogger,
    ) -> None:
        super().__init__(worktree, runner_root, state_path, logger)  # type: ignore[arg-type]
        self.new_amendment_path = self.worktree / NEW_AMENDMENT_RELATIVE_PATH
        self.lifecycle_correction_path = (
            self.worktree / LIFECYCLE_CORRECTION_RELATIVE_PATH
        )
        self.engineering_correction_path = (
            self.worktree / ENGINEERING_CORRECTION_RELATIVE_PATH
        )
        self.network_correction_path = (
            self.worktree / NETWORK_CORRECTION_RELATIVE_PATH
        )
        self.structured_output_correction_path = (
            self.worktree / STRUCTURED_OUTPUT_CORRECTION_RELATIVE_PATH
        )
        self.evidence_reference_correction_path = (
            self.worktree / EVIDENCE_REFERENCE_CORRECTION_RELATIVE_PATH
        )
        self.canonical_reconciliation_correction_path = (
            self.worktree / CANONICAL_RECONCILIATION_CORRECTION_RELATIVE_PATH
        )
        self.topology_correction_path = (
            self.worktree / TOPOLOGY_CORRECTION_RELATIVE_PATH
        )

    def actual_head(self) -> str:
        return self._git("rev-parse", "HEAD").strip()

    def branch(self) -> str:
        return self._git("branch", "--show-current").strip()

    def _repository_python_environment(self) -> dict[str, str]:
        environment = legacy.sanitized_environment()
        environment["PYTHONPATH"] = str(self.worktree / "src")
        return environment

    def validate_materialized_position(self, position: int) -> None:
        command = [
            sys.executable,
            str(self.worktree / MATERIALIZER_RELATIVE_PATH),
            "--repository-root",
            str(self.worktree),
            "--expected-position",
            str(position),
            "--validate-existing",
        ]
        completed = subprocess.run(
            command,
            cwd=self.worktree,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            env=self._repository_python_environment(),
        )
        if completed.returncode != 0:
            raise RunnerError(
                "materialized position validation failed: "
                + (completed.stderr.strip() or completed.stdout.strip())
            )

    def validate_tptm_bundle(self, position: int) -> None:
        root = self.position_path(position)
        result = root / "tptm-result.json"
        routing = root / "hybrid-routing.json"
        command = [sys.executable, "-m", "cmpilot.tptm.cli"]
        validated = subprocess.run(
            [*command, "validate-result", "--result", str(result)],
            cwd=self.worktree,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=self._repository_python_environment(),
        )
        if validated.returncode != 0:
            raise RunnerError("TPTM result validation failed")
        replay = subprocess.run(
            [*command, "hybrid-route", "--result", str(result)],
            cwd=self.worktree,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=self._repository_python_environment(),
        )
        if replay.returncode != 0 or replay.stdout != routing.read_bytes():
            raise RunnerError("hybrid routing is not the canonical TPTM projection")
        envelope = read_json(root / "tptm-run-envelope.json")
        expected_input = str(
            RUN_RELATIVE_PATH / "positions" / f"{position:08d}" / "candidate-manifest.json"
        )
        expected_output = str(
            RUN_RELATIVE_PATH / "positions" / f"{position:08d}" / "tptm-result.json"
        )
        if (
            not isinstance(envelope, dict)
            or envelope.get("schema_version") != "tptm-run-envelope-v1"
            or envelope.get("analysis_version") != "tptm-analysis-v1"
            or envelope.get("operation") != "analyze-manifest"
            or envelope.get("input_path") != expected_input
            or envelope.get("output_path") != expected_output
            or isinstance(envelope.get("exit_code"), bool)
            or envelope.get("exit_code") not in {0, 2, 3, 4, 5}
        ):
            raise RunnerError("TPTM run envelope binding differs")

    def validate_review_packet(self, position: int) -> None:
        packet = self.position_path(position) / "review-packet.json"
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "cmpilot.tptm.cli",
                "validate-review-packet",
                "--packet",
                str(packet),
            ],
            cwd=self.worktree,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=self._repository_python_environment(),
        )
        if completed.returncode != 0:
            raise RunnerError("review packet validation failed")

    @staticmethod
    def _validate_self_hash(value: Mapping[str, Any], field: str) -> None:
        expected = value.get(field)
        if not isinstance(expected, str) or legacy.SHA256_RE.fullmatch(expected) is None:
            raise RunnerError(f"{field} is not a frozen SHA-256 identity")

    def validate_combined_review(self, position: int, path: Path) -> dict[str, Any]:
        value = read_json(path)
        if not isinstance(value, dict):
            raise RunnerError("combined review must be an object")
        required = {
            "schema",
            "protocol_id",
            "screening_method_version",
            "queue_position",
            "candidate_id",
            "review_packet_sha256",
            "reviewer_a_decision_sha256",
            "reviewer_b_decision_sha256",
            "reviewer_a_outcome",
            "reviewer_b_outcome",
            "semantic_decision_disagreement",
            "question_disagreements",
            "focal_hypothesis_disagreement",
            "reviewer_a_focal_hypothesis",
            "reviewer_b_focal_hypothesis",
            "combined_outcome",
            "authorized_next_action",
            "combined_review_sha256",
        }
        if set(value) != required:
            raise RunnerError("combined review fields are not exact")
        self._validate_self_hash(value, "combined_review_sha256")
        first = self.validate_ai_decision(
            self.position_path(position) / "ai-reviewer-a-decision.json",
            legacy.Role.AI_FIRST_REVIEW,
        )
        second = self.validate_ai_decision(
            self.position_path(position) / "ai-reviewer-b-decision.json",
            legacy.Role.AI_SECOND_REVIEW,
        )
        outcome, action = legacy.combine_review_metadata(
            first["semantic_decision"], second["semantic_decision"]
        )
        semantic_a = first["semantic_decision"]
        semantic_b = second["semantic_decision"]
        answers_a = {
            row.get("question_id"): row
            for row in semantic_a.get("answers", [])
            if isinstance(row, Mapping)
        }
        answers_b = {
            row.get("question_id"): row
            for row in semantic_b.get("answers", [])
            if isinstance(row, Mapping)
        }
        question_ids = {f"Q{index}" for index in range(1, 11)}
        if set(answers_a) != question_ids or set(answers_b) != question_ids:
            raise RunnerError("combined review question vectors are incomplete")
        disagreements = {
            question_id: answers_a[question_id] != answers_b[question_id]
            for question_id in sorted(question_ids, key=lambda item: int(item[1:]))
        }
        if (
            value.get("schema") != "candidate-screening-combined-review-v0.2.0"
            or value.get("protocol_id") != "candidate-screening-v0.2.0"
            or value.get("screening_method_version") != "tptm-hybrid-screening-v1"
            or value.get("queue_position") != position
            or value.get("candidate_id") != semantic_a["candidate_id"]
            or value.get("candidate_id") != semantic_b["candidate_id"]
            or value.get("review_packet_sha256")
            != semantic_a["review_packet_sha256"]
            or value.get("review_packet_sha256")
            != semantic_b["review_packet_sha256"]
            or value.get("reviewer_a_decision_sha256") != first["decision_sha256"]
            or value.get("reviewer_b_decision_sha256") != second["decision_sha256"]
            or value.get("reviewer_a_outcome") != semantic_a["outcome"]
            or value.get("reviewer_b_outcome") != semantic_b["outcome"]
            or value.get("semantic_decision_disagreement")
            is not (semantic_a["outcome"] != semantic_b["outcome"])
            or value.get("question_disagreements") != disagreements
            or value.get("reviewer_a_focal_hypothesis")
            != semantic_a["focal_hypothesis"]
            or value.get("reviewer_b_focal_hypothesis")
            != semantic_b["focal_hypothesis"]
            or value.get("focal_hypothesis_disagreement")
            is not (
                semantic_a["focal_hypothesis"] != semantic_b["focal_hypothesis"]
            )
            or value.get("combined_outcome") != outcome
            or value.get("authorized_next_action") != action
        ):
            raise RunnerError("combined review differs from frozen exact combination")
        return value

    def validate_family_metadata(
        self, position: int, path: Path, combined: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        value = read_json(path)
        if not isinstance(value, dict):
            raise RunnerError("family feasibility must be an object")
        required = {
            "schema",
            "protocol_id",
            "screening_method_version",
            "queue_position",
            "candidate_id",
            "combined_review_sha256",
            "required",
            "attempted",
            "focal_hypothesis_handling",
            "tptm_family_recipes_count",
            "tptm_trust_transitions_count",
            "tptm_witness_candidates_count",
            "family_construction_state",
            "family_recipe_sha256",
            "executable_validation_state",
            "admission_state",
            "outcome",
            "reason_code",
            "family_feasibility_sha256",
        }
        if set(value) != required:
            raise RunnerError("family feasibility fields are not exact")
        self._validate_self_hash(value, "family_feasibility_sha256")
        authorization = read_json(
            self.position_path(position) / "position-authorization.json"
        )
        expected_candidate = (
            combined.get("candidate_id")
            if combined is not None
            else authorization.get("candidate_id")
        )
        counts = (
            value.get("tptm_family_recipes_count"),
            value.get("tptm_trust_transitions_count"),
            value.get("tptm_witness_candidates_count"),
        )
        if (
            value.get("schema") != "candidate-screening-family-feasibility-v0.2.0"
            or value.get("protocol_id") != "candidate-screening-v0.2.0"
            or value.get("screening_method_version") != "tptm-hybrid-screening-v1"
            or value.get("queue_position") != position
            or value.get("candidate_id") != expected_candidate
            or not isinstance(value.get("required"), bool)
            or not isinstance(value.get("attempted"), bool)
            or any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in counts)
        ):
            raise RunnerError("family feasibility position binding differs")
        if combined is not None and value.get("combined_review_sha256") != combined.get(
            "combined_review_sha256"
        ):
            raise RunnerError("family feasibility combined-review binding differs")
        if value.get("reason_code") == (
            "NO_UNIQUE_FOCAL_HYPOTHESIS_UNDER_FROZEN_DISAGREEMENT_POLICY"
        ) and (
            value.get("family_construction_state") != "FAILED"
            or value.get("family_recipe_sha256") is not None
            or value.get("executable_validation_state") != "NOT_APPLICABLE"
            or value.get("admission_state") != "NOT_APPLICABLE"
        ):
            raise RunnerError("no-unique-focal family failure semantics differ")
        return value

    def validate_executable_metadata(
        self, position: int, path: Path, family: Mapping[str, Any]
    ) -> dict[str, Any]:
        value = read_json(path)
        required = {
            "schema",
            "protocol_id",
            "screening_method_version",
            "queue_position",
            "candidate_id",
            "family_feasibility_sha256",
            "family_feasibility_file_sha256",
            "family_recipe_sha256",
            "validation_state",
            "p_star_source",
            "p_star_compatible",
            "p_star_invalidated",
            "functional_oracles_state",
            "reuse_witness_state",
            "safe_witness_state",
            "focal_trust_change_count",
            "repository_independence_state",
            "trust_category",
            "evidence_paths",
            "evidence_sha256",
            "executable_validation_sha256",
        }
        if not isinstance(value, dict) or set(value) != required:
            raise RunnerError("family executable-validation fields are not exact")
        digest = value.get("executable_validation_sha256")
        payload = {
            key: item
            for key, item in value.items()
            if key != "executable_validation_sha256"
        }
        if (
            not isinstance(digest, str)
            or digest != sha256_bytes(legacy.canonical_json_bytes(payload))
        ):
            raise RunnerError("family executable-validation SHA-256 differs")
        family_path = self.position_path(position) / "family-feasibility.json"
        paths = value.get("evidence_paths")
        hashes = value.get("evidence_sha256")
        prefix = f"{RUN_RELATIVE_PATH}/positions/{position:08d}/"
        if (
            value.get("schema")
            != "candidate-screening-family-executable-validation-v0.1"
            or value.get("protocol_id") != "candidate-screening-v0.2.0"
            or value.get("screening_method_version") != "tptm-hybrid-screening-v1"
            or value.get("queue_position") != position
            or value.get("candidate_id") != family.get("candidate_id")
            or value.get("family_feasibility_sha256")
            != family.get("family_feasibility_sha256")
            or value.get("family_feasibility_file_sha256")
            != sha256_file(family_path)
            or value.get("family_recipe_sha256")
            != family.get("family_recipe_sha256")
            or value.get("validation_state") not in {"PASSED", "FAILED"}
            or not isinstance(paths, list)
            or not paths
            or paths != sorted(set(paths))
            or not isinstance(hashes, dict)
            or set(hashes) != set(paths)
        ):
            raise RunnerError("family executable-validation binding differs")
        for raw in paths:
            if not isinstance(raw, str) or not raw.startswith(prefix):
                raise RunnerError("executable evidence crosses the current position")
            relative = self._safe_relative(raw)
            evidence = self.worktree / relative
            if (
                evidence.is_symlink()
                or not evidence.is_file()
                or hashes.get(raw) != sha256_file(evidence)
            ):
                raise RunnerError("executable evidence hash differs")
        if value["validation_state"] == "PASSED" and (
            value.get("p_star_source") is not True
            or value.get("p_star_compatible") is not True
            or value.get("p_star_invalidated") is not False
            or value.get("functional_oracles_state") != "PASS"
            or value.get("reuse_witness_state") != "TRIGGERED"
            or value.get("safe_witness_state") != "BLOCKED"
            or value.get("focal_trust_change_count") != 1
            or value.get("repository_independence_state") != "PASS"
            or not isinstance(value.get("trust_category"), str)
            or not value["trust_category"]
        ):
            raise RunnerError("executable evidence does not satisfy frozen final authority")
        return value

    def validate_terminal_evidence(
        self, position: int, record: Mapping[str, Any]
    ) -> None:
        processing = record.get("processing_state")
        if processing not in {
            "FAMILY_CONSTRUCTION_FAILED",
            "FAMILY_VALIDATION_FAILED",
            "ADMIT_FINAL",
            "VALIDATED_NOT_ADMITTED_CATEGORY_CAP",
            "VALIDATED_NOT_ADMITTED_REPOSITORY_GROUP",
        }:
            return
        root = self.position_path(position)
        combined = None
        if (root / "combined-review.json").is_file():
            combined = self.validate_combined_review(
                position, root / "combined-review.json"
            )
        family = self.validate_family_metadata(
            position, root / "family-feasibility.json", combined
        )
        if processing == "FAMILY_CONSTRUCTION_FAILED":
            if family.get("family_construction_state") != "FAILED":
                raise RunnerError("terminal construction failure lacks failed construction")
            return
        executable = self.validate_executable_metadata(
            position, root / "family-executable-validation.json", family
        )
        if processing == "FAMILY_VALIDATION_FAILED":
            if executable.get("validation_state") != "FAILED":
                raise RunnerError("terminal validation failure lacks failed executable evidence")
            return
        if (
            executable.get("validation_state") != "PASSED"
            or record.get("family_executable_validation_state") != "PASSED"
            or record.get("family_recipe_sha256")
            != executable.get("family_recipe_sha256")
            or record.get("admission_state") != processing
        ):
            raise RunnerError("terminal admission is not bound to executable authority")

    def discovery_materialization_ready(self) -> bool:
        transaction = self.worktree / (
            "benchmark-selection/discovery/runs/v0.3/"
            "full-production-resume-20260819T033500Z-9bc403174"
        )
        required = (
            transaction / "candidate-pool.jsonl",
            transaction / "candidate-pool.jsonl.sha256",
            transaction / "candidate-pool-manifest.json",
            transaction / "candidate-pool-manifest.json.sha256",
            transaction / "sources",
        )
        return all(path.exists() and not path.is_symlink() for path in required)

    def b_assignment_completion_permitted(self, path: Path, position: int) -> bool:
        try:
            value = read_json(path)
        except legacy.RunnerError:
            return False
        if not isinstance(value, dict):
            return False
        copied = {
            "candidate_id",
            "review_packet",
            "permitted_evidence_paths",
            "permitted_evidence_sha256",
            "permitted_interface_paths",
            "permitted_interface_sha256",
        }
        required = {
            "schema_version",
            "amendment_id",
            "protocol_version",
            "status",
            "created_at_utc",
            "queue_position",
            "reviewer_type",
            "reviewer_role",
            "authoritative",
            "required_execution_boundary",
            *copied,
            "decision_output_path",
            "prohibited_information_boundary",
            "terminal_record_published",
            "ledger_updated",
        }
        if not set(value) <= required or not required - copied <= set(value):
            return False
        try:
            assignment_a = self.validate_assignment(
                self.position_path(position) / "ai-reviewer-a-assignment.json",
                legacy.Role.AI_FIRST_REVIEW,
            )
        except legacy.RunnerError:
            return False
        if any(
            key in value and value[key] != assignment_a[key]
            for key in copied
        ):
            return False
        expected_boundary = {
            "ai_reviewer_a_vector": True,
            "ai_reviewer_a_reasoning": True,
            "ai_reviewer_a_outcome": True,
            "ai_reviewer_a_focal_hypothesis": True,
            "ai_reviewer_a_source_condition_finding": True,
            "combined_result": True,
            "final_outcome": True,
            "admission_status": True,
            "scoring_or_gold_labels": True,
            "unrelated_candidate_outcomes": True,
            "future_queue_material": True,
            "track_b_material": True,
        }
        expected_output = str(
            RUN_RELATIVE_PATH
            / "positions"
            / f"{position:08d}"
            / "ai-reviewer-b-decision.json"
        )
        if (
            value.get("schema_version")
            != "candidate-screening-ai-review-assignment-v0.1"
            or value.get("amendment_id") != legacy.AMENDMENT_ID
            or value.get("protocol_version") != "candidate-screening-v0.2.0"
            or value.get("status") != "AWAITING_AUTHORITATIVE_AI_REVIEW"
            or value.get("queue_position") != position
            or value.get("reviewer_type") != "AI"
            or value.get("reviewer_role") != "AI_SECOND_REVIEW"
            or value.get("authoritative") is not True
            or value.get("required_execution_boundary")
            != "FRESH_ONE_SHOT_CODEX_PROCESS"
            or value.get("decision_output_path") != expected_output
            or value.get("prohibited_information_boundary") != expected_boundary
            or value.get("terminal_record_published") is not False
            or value.get("ledger_updated") is not False
        ):
            return False
        paths: list[str] = []
        for key in ("permitted_evidence_paths", "permitted_interface_paths"):
            candidate = value.get(key, [])
            if not isinstance(candidate, list) or any(
                not isinstance(item, str) for item in candidate
            ):
                return False
            paths.extend(candidate)
        serialized_paths = "\n".join(paths).lower()
        return not any(
            fragment in serialized_paths for fragment in legacy.FORBIDDEN_B_PATH_FRAGMENTS
        )

    def _snapshot_at_actual_head(self) -> legacy.Snapshot:
        head = self.actual_head()
        self._verify_sidecar(self.ledger_path, self.ledger_sidecar_path)
        ledger = read_json(self.ledger_path)
        if not isinstance(ledger, dict):
            raise RunnerError("ledger must be an object")
        count = ledger.get("records_published")
        paths = ledger.get("record_paths")
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or not isinstance(paths, list)
            or len(paths) != count
        ):
            raise RunnerError("ledger publication sequence is invalid")
        records = [
            read_json(self.run_path / "records" / f"{position:08d}.json")
            for position in range(1, count + 1)
        ]
        self._replay_ledger(ledger, records)
        for position in range(legacy.EFFECTIVE_POSITION, count + 1):
            self._verify_amended_terminal_record(position, records[position - 1])
            self.validate_terminal_evidence(position, records[position - 1])
        state = ledger.get("state")
        if not isinstance(state, dict):
            raise RunnerError("ledger state is absent")
        snapshot = legacy.Snapshot(
            head=head,
            records_published=state["records_published"],
            successor_positions_processed=state["successor_positions_processed"],
            historical_unique_opened_anchors=state["historical_unique_opened_anchors"],
            global_unique_opened_anchors=state["global_unique_opened_anchors"],
            final=state["FINAL"],
            categories_represented=state["trust_categories_represented"],
            next_due_position=state["next_due_position"],
            global_action=state["global_action"],
        )
        if (
            snapshot.records_published != count
            or snapshot.successor_positions_processed != count
            or snapshot.next_due_position != count + 1
            or snapshot.historical_unique_opened_anchors != 2
        ):
            raise RunnerError("ledger sequential accounting differs")
        self._last_snapshot = snapshot
        return snapshot

    def snapshot(self) -> legacy.Snapshot:
        snapshot = self._snapshot_at_actual_head()
        if snapshot.head != self.state["expected_head"]:
            raise RunnerError("actual HEAD requires startup/role reconciliation")
        return snapshot

    def preflight(self, *, dry_run: bool, codex_bin: Path | None) -> legacy.Snapshot:
        if self.branch() != EXPECTED_BRANCH:
            raise RunnerError(f"production branch differs: {self.branch()}")
        if self.runner_root == self.worktree or self.worktree in self.runner_root.parents:
            raise RunnerError("runner root must remain outside production worktree")
        validate_runtime_interface_coverage(self.worktree)
        self._verify_amendment_chain()
        self._repair_valid_ledger_sidecar_if_needed(dry_run=dry_run)
        snapshot = self._snapshot_at_actual_head()
        self._reconcile_expected_head(snapshot)
        self._validate_worktree_boundary(snapshot.next_due_position)
        if not dry_run:
            snapshot = self._reconcile_uncommitted_startup(snapshot)
            verify_codex_cli(codex_bin, self.worktree)
        snapshot = self.snapshot()
        classification = DurableClassifier(self).classify(snapshot)
        validate_reachable_recovery_inputs(
            self, classification, snapshot.next_due_position
        )
        return snapshot

    def _reconcile_uncommitted_startup(
        self, snapshot: legacy.Snapshot
    ) -> legacy.Snapshot:
        pending = self.uncommitted_current_paths(
            snapshot.next_due_position, include_previous=True
        )
        if not pending:
            return snapshot
        try:
            committed_ledger = json.loads(
                self._git("show", f"HEAD:{RUN_RELATIVE_PATH}/ledger.json")
            )
        except (json.JSONDecodeError, legacy.RunnerError) as error:
            raise RunnerError("committed ledger boundary is unreadable") from error
        committed_count = committed_ledger.get("records_published")
        if snapshot.records_published == committed_count + 1:
            completed_position = snapshot.records_published
            allowed = {
                self.run_path / "records" / f"{completed_position:08d}.json",
                self.ledger_path,
                self.ledger_sidecar_path,
            }
            allowed_prefix = self.position_path(completed_position)
            if any(
                path not in allowed
                and path != allowed_prefix
                and allowed_prefix not in path.parents
                for path in pending
            ):
                raise RunnerError("interrupted publication contains unrelated paths")
            self._commit_paths(
                f"Reconcile interrupted position {completed_position} publication commit",
                pending,
                completed_position,
            )
            return self.snapshot()
        if snapshot.records_published != committed_count:
            raise RunnerError("uncommitted ledger transition is not a unit publication")
        classification = DurableClassifier(self).classify(snapshot)
        if classification.recovery_id is not None or classification.state in {
            DurableState.POST_ROLE_RECONCILIATION_REQUIRED,
            DurableState.PARTIAL_PUBLICATION_RECONCILIATION,
        }:
            return snapshot
        self.commit_valid_uncommitted_transition(
            snapshot.next_due_position, classification
        )
        return self.snapshot()

    def _repair_valid_ledger_sidecar_if_needed(self, *, dry_run: bool) -> None:
        digest = sha256_file(self.ledger_path)
        expected = f"{digest}  ledger.json\n"
        observed = None
        if self.ledger_sidecar_path.is_file() and not self.ledger_sidecar_path.is_symlink():
            try:
                observed = self.ledger_sidecar_path.read_text(encoding="ascii")
            except (OSError, UnicodeError):
                observed = None
        if observed == expected:
            return
        ledger = read_json(self.ledger_path)
        if not isinstance(ledger, dict):
            raise RunnerError("ledger checksum differs and ledger is not an object")
        count = ledger.get("records_published")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise RunnerError("ledger checksum differs and record count is invalid")
        records = [
            read_json(self.run_path / "records" / f"{position:08d}.json")
            for position in range(1, count + 1)
        ]
        self._replay_ledger(ledger, records)
        if dry_run:
            raise RunnerError(
                "valid ledger has an interrupted checksum write; deterministic recovery required"
            )
        _atomic_bytes(self.ledger_sidecar_path, expected.encode("ascii"))
        paths = [self.ledger_sidecar_path]
        relative = str(self.ledger_sidecar_path.relative_to(self.worktree))
        subprocess.run(
            ["git", "add", "--", relative],
            cwd=self.worktree,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=legacy.sanitized_environment(),
        )
        commit = subprocess.run(
            ["git", "commit", "-m", "Reconcile interrupted Track A ledger checksum"],
            cwd=self.worktree,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=legacy.sanitized_environment(),
        )
        if commit.returncode != 0:
            raise RunnerError(
                f"ledger checksum recovery commit failed: {commit.stderr.strip()}"
            )
        actual = self.actual_head()
        self._accept_new_head(actual)
        self.logger.emit_event(
            EventType.RECOVERY_REQUIRED,
            recovery_id="INTERRUPTED_TERMINAL_PUBLICATION_RECONCILIATION",
            position=count,
            head=actual,
            paths=[str(path) for path in paths],
            reason="validated ledger checksum write completed and committed",
        )

    def _verify_amendment_chain(
        self, *, require_state_binding: bool = True
    ) -> dict[str, Any]:
        # First validate repository-owned bytes in both predecessor freezes.  Their
        # external live-path hashes are intentionally superseded by the new freeze.
        for root, identity_key, identity in (
            (self.amendment_path, "amendment_id", legacy.AMENDMENT_ID),
            (self.correction_path, "correction_id", legacy.CORRECTION_ID),
        ):
            manifest_path = root / "freeze-manifest.json"
            self._verify_sidecar(manifest_path, root / "freeze-manifest.json.sha256")
            manifest = read_json(manifest_path)
            if not isinstance(manifest, dict) or manifest.get(identity_key) != identity:
                raise RunnerError(f"predecessor freeze identity differs: {root.name}")
            for artifact in manifest.get("artifacts", []):
                raw = artifact.get("path")
                if not isinstance(raw, str):
                    raise RunnerError("predecessor artifact path is invalid")
                path = self.worktree / PurePosixPath(raw)
                if not path.is_file() or sha256_file(path) != artifact.get("sha256"):
                    raise RunnerError(f"predecessor frozen artifact mismatch: {raw}")
        parent_manifest_path = self.new_amendment_path / "freeze-manifest.json"
        self._verify_sidecar(
            parent_manifest_path,
            self.new_amendment_path / "freeze-manifest.json.sha256",
        )
        parent_manifest = read_json(parent_manifest_path)
        if (
            not isinstance(parent_manifest, dict)
            or parent_manifest.get("amendment_id") != NEW_AMENDMENT_ID
            or parent_manifest.get("effective_from_position") != 22
            or parent_manifest.get("scientific_methodology_changed") is not False
        ):
            raise RunnerError("durable orchestration amendment identity differs")
        for artifact in parent_manifest.get("repository_artifacts", []):
            raw = artifact.get("path")
            path = self.worktree / PurePosixPath(raw)
            if not path.is_file() or sha256_file(path) != artifact.get("sha256"):
                raise RunnerError(f"new frozen repository artifact mismatch: {raw}")

        # The lifecycle correction superseded only the parent's external live
        # paths.  Its external hashes are now historical evidence superseded by
        # the append-only pre-production integrity correction below.
        manifest_path = self.lifecycle_correction_path / "freeze-manifest.json"
        self._verify_sidecar(
            manifest_path,
            self.lifecycle_correction_path / "freeze-manifest.json.sha256",
        )
        manifest = read_json(manifest_path)
        parent_binding = (
            manifest.get("parent_orchestration_amendment", {})
            if isinstance(manifest, dict)
            else {}
        )
        if (
            not isinstance(manifest, dict)
            or manifest.get("correction_id") != LIFECYCLE_CORRECTION_ID
            or manifest.get("effective_from_position") != 22
            or manifest.get("scientific_methodology_changed") is not False
            or manifest.get("reviewer_authority_changed") is not False
            or manifest.get("track_b_modified") is not False
            or not isinstance(parent_binding, dict)
            or parent_binding.get("amendment_id") != NEW_AMENDMENT_ID
            or parent_binding.get("freeze_manifest_sha256")
            != sha256_file(parent_manifest_path)
        ):
            raise RunnerError("runner lifecycle correction identity differs")
        for artifact in manifest.get("repository_artifacts", []):
            raw = artifact.get("path")
            if not isinstance(raw, str):
                raise RunnerError("lifecycle correction artifact path is invalid")
            path = self.worktree / PurePosixPath(raw)
            if not path.is_file() or sha256_file(path) != artifact.get("sha256"):
                raise RunnerError(f"lifecycle correction artifact mismatch: {raw}")
        integrity_manifest_path = self.engineering_correction_path / "freeze-manifest.json"
        self._verify_sidecar(
            integrity_manifest_path,
            self.engineering_correction_path / "freeze-manifest.json.sha256",
        )
        integrity_manifest = read_json(integrity_manifest_path)
        predecessor_binding = (
            integrity_manifest.get("predecessor_lifecycle_correction", {})
            if isinstance(integrity_manifest, dict)
            else {}
        )
        if (
            not isinstance(integrity_manifest, dict)
            or integrity_manifest.get("correction_id") != ENGINEERING_CORRECTION_ID
            or integrity_manifest.get("effective_from_position") != 22
            or integrity_manifest.get("scientific_methodology_changed") is not False
            or integrity_manifest.get("reviewer_authority_changed") is not False
            or integrity_manifest.get("track_b_modified") is not False
            or integrity_manifest.get("position_22_unchanged") is not True
            or integrity_manifest.get("position_23_unopened") is not True
            or not isinstance(predecessor_binding, dict)
            or predecessor_binding.get("correction_id") != LIFECYCLE_CORRECTION_ID
            or predecessor_binding.get("freeze_manifest_sha256")
            != sha256_file(manifest_path)
        ):
            raise RunnerError("pre-production integrity correction identity differs")
        for artifact in integrity_manifest.get("repository_artifacts", []):
            raw = artifact.get("path")
            if not isinstance(raw, str):
                raise RunnerError("integrity correction artifact path is invalid")
            path = self.worktree / PurePosixPath(raw)
            if not path.is_file() or sha256_file(path) != artifact.get("sha256"):
                raise RunnerError(f"integrity correction artifact mismatch: {raw}")
        network_manifest_path = self.network_correction_path / "freeze-manifest.json"
        self._verify_sidecar(
            network_manifest_path,
            self.network_correction_path / "freeze-manifest.json.sha256",
        )
        network_manifest = read_json(network_manifest_path)
        network_predecessor = (
            network_manifest.get("predecessor_integrity_correction", {})
            if isinstance(network_manifest, dict)
            else {}
        )
        if (
            not isinstance(network_manifest, dict)
            or network_manifest.get("correction_id") != NETWORK_CORRECTION_ID
            or network_manifest.get("effective_from_position") != 22
            or network_manifest.get("observed_canary_run_id")
            != "20260829T050206Z-4ad21fdfd5b4"
            or network_manifest.get("scientific_methodology_changed") is not False
            or network_manifest.get("reviewer_authority_changed") is not False
            or network_manifest.get("track_b_modified") is not False
            or network_manifest.get("position_22_durable_state")
            != "AI_FIRST_REVIEW_REQUIRED"
            or network_manifest.get("position_22_unchanged") is not True
            or network_manifest.get("position_23_unopened") is not True
            or not isinstance(network_predecessor, dict)
            or network_predecessor.get("correction_id") != ENGINEERING_CORRECTION_ID
            or network_predecessor.get("freeze_manifest_sha256")
            != sha256_file(integrity_manifest_path)
            or network_predecessor.get("operational_amendment_sha256")
            != sha256_file(
                self.engineering_correction_path / "operational-amendment.json"
            )
        ):
            raise RunnerError("network recovery correction identity differs")
        for artifact in network_manifest.get("repository_artifacts", []):
            raw = artifact.get("path")
            if not isinstance(raw, str):
                raise RunnerError("network correction artifact path is invalid")
            path = self.worktree / PurePosixPath(raw)
            if not path.is_file() or sha256_file(path) != artifact.get("sha256"):
                raise RunnerError(f"network correction artifact mismatch: {raw}")
        # The structured-output correction below supersedes only the network
        # correction's live external hashes.  Its repository bytes remain frozen.
        structured_manifest_path = (
            self.structured_output_correction_path / "freeze-manifest.json"
        )
        self._verify_sidecar(
            structured_manifest_path,
            self.structured_output_correction_path / "freeze-manifest.json.sha256",
        )
        structured_manifest = read_json(structured_manifest_path)
        structured_predecessor = (
            structured_manifest.get("predecessor_network_correction", {})
            if isinstance(structured_manifest, dict)
            else {}
        )
        if (
            not isinstance(structured_manifest, dict)
            or structured_manifest.get("correction_id")
            != STRUCTURED_OUTPUT_CORRECTION_ID
            or structured_manifest.get("effective_from_position") != 22
            or structured_manifest.get("failed_canary_run_id")
            != "20260829T124909Z-9bed6300ca78"
            or structured_manifest.get("scientific_methodology_changed") is not False
            or structured_manifest.get("canonical_scientific_schema_changed") is not False
            or structured_manifest.get("reviewer_authority_changed") is not False
            or structured_manifest.get("reviewer_b_blinding_changed") is not False
            or structured_manifest.get("track_b_modified") is not False
            or structured_manifest.get("position_22_durable_state")
            != "AI_FIRST_REVIEW_REQUIRED"
            or structured_manifest.get("position_22_unchanged") is not True
            or structured_manifest.get("position_23_unopened") is not True
            or not isinstance(structured_predecessor, dict)
            or structured_predecessor.get("correction_id") != NETWORK_CORRECTION_ID
            or structured_predecessor.get("freeze_manifest_sha256")
            != sha256_file(network_manifest_path)
            or structured_predecessor.get("operational_amendment_sha256")
            != sha256_file(
                self.network_correction_path / "operational-amendment.json"
            )
        ):
            raise RunnerError("structured-output correction identity differs")
        for artifact in structured_manifest.get("repository_artifacts", []):
            raw = artifact.get("path")
            if not isinstance(raw, str):
                raise RunnerError("structured-output artifact path is invalid")
            path = self.worktree / PurePosixPath(raw)
            if not path.is_file() or sha256_file(path) != artifact.get("sha256"):
                raise RunnerError(f"structured-output artifact mismatch: {raw}")
        # The evidence-reference correction supersedes only the structured-output
        # correction's live external hashes.  Its repository bytes remain frozen.
        evidence_manifest_path = (
            self.evidence_reference_correction_path / "freeze-manifest.json"
        )
        self._verify_sidecar(
            evidence_manifest_path,
            self.evidence_reference_correction_path / "freeze-manifest.json.sha256",
        )
        evidence_manifest = read_json(evidence_manifest_path)
        evidence_predecessor = (
            evidence_manifest.get("predecessor_structured_output_correction", {})
            if isinstance(evidence_manifest, dict)
            else {}
        )
        if (
            not isinstance(evidence_manifest, dict)
            or evidence_manifest.get("correction_id")
            != EVIDENCE_REFERENCE_CORRECTION_ID
            or evidence_manifest.get("effective_from_position") != 22
            or evidence_manifest.get("exact_starting_head")
            != "7f4325a38304fc41fab308056ac97dc01817aed8"
            or evidence_manifest.get("observed_canary_run_id")
            != "20260829T144300Z-24c7f642fa66"
            or evidence_manifest.get("scientific_methodology_changed") is not False
            or evidence_manifest.get("canonical_scientific_schema_changed") is not False
            or evidence_manifest.get("canonical_validator_changed") is not False
            or evidence_manifest.get("reviewer_authority_changed") is not False
            or evidence_manifest.get("reviewer_b_blinding_changed") is not False
            or evidence_manifest.get("track_b_modified") is not False
            or evidence_manifest.get("position_22_durable_state")
            != "AI_FIRST_REVIEW_REQUIRED"
            or evidence_manifest.get("position_22_unchanged") is not True
            or evidence_manifest.get("position_23_unopened") is not True
            or evidence_manifest.get("superseded_external_runner_artifacts")
            != structured_manifest.get("external_runner_artifacts")
            or not isinstance(evidence_predecessor, dict)
            or evidence_predecessor.get("correction_id")
            != STRUCTURED_OUTPUT_CORRECTION_ID
            or evidence_predecessor.get("freeze_manifest_sha256")
            != sha256_file(structured_manifest_path)
            or evidence_predecessor.get("operational_amendment_sha256")
            != sha256_file(
                self.structured_output_correction_path / "operational-amendment.json"
            )
        ):
            raise RunnerError("evidence-reference correction identity differs")
        for artifact in evidence_manifest.get("repository_artifacts", []):
            raw = artifact.get("path")
            if not isinstance(raw, str):
                raise RunnerError("evidence-reference artifact path is invalid")
            path = self.worktree / PurePosixPath(raw)
            if not path.is_file() or sha256_file(path) != artifact.get("sha256"):
                raise RunnerError(f"evidence-reference artifact mismatch: {raw}")
        # The canonical-reconciliation correction supersedes only the evidence
        # correction's live external hashes.  The predecessor's pre-canary
        # boundary and repository bytes remain immutable historical evidence.
        canonical_manifest_path = (
            self.canonical_reconciliation_correction_path / "freeze-manifest.json"
        )
        self._verify_sidecar(
            canonical_manifest_path,
            self.canonical_reconciliation_correction_path
            / "freeze-manifest.json.sha256",
        )
        canonical_manifest = read_json(canonical_manifest_path)
        canonical_predecessor = (
            canonical_manifest.get("predecessor_evidence_reference_correction", {})
            if isinstance(canonical_manifest, dict)
            else {}
        )
        if (
            not isinstance(canonical_manifest, dict)
            or canonical_manifest.get("correction_id")
            != CANONICAL_RECONCILIATION_CORRECTION_ID
            or canonical_manifest.get("effective_from_position") != 22
            or canonical_manifest.get("exact_starting_head")
            != "90046c1bbcf2784086f201510ca4ac253a093c7a"
            or canonical_manifest.get("observed_canary_run_id")
            != "20260829T154912Z-03ee44c42379"
            or canonical_manifest.get("authoritative_ai_a_decision_sha256")
            != "06465e9f58a4d03ecaa09390b62571903ccb6e13edde73ae9cb9cc744c6c79ea"
            or canonical_manifest.get("position_22_durable_state")
            != "AI_SECOND_ASSIGNMENT_REQUIRED"
            or canonical_manifest.get("authoritative_ai_a_decision_preserved") is not True
            or canonical_manifest.get("position_23_unopened") is not True
            or canonical_manifest.get("scientific_methodology_changed") is not False
            or canonical_manifest.get("canonical_scientific_schema_changed") is not False
            or canonical_manifest.get("canonical_validator_changed") is not False
            or canonical_manifest.get("reviewer_authority_changed") is not False
            or canonical_manifest.get("reviewer_b_blinding_changed") is not False
            or canonical_manifest.get("track_b_modified") is not False
            or canonical_manifest.get("superseded_external_runner_artifacts")
            != evidence_manifest.get("external_runner_artifacts")
            or not isinstance(canonical_predecessor, dict)
            or canonical_predecessor.get("correction_id")
            != EVIDENCE_REFERENCE_CORRECTION_ID
            or canonical_predecessor.get("freeze_manifest_sha256")
            != sha256_file(evidence_manifest_path)
            or canonical_predecessor.get("operational_amendment_sha256")
            != sha256_file(
                self.evidence_reference_correction_path / "operational-amendment.json"
            )
        ):
            raise RunnerError("canonical reconciliation correction identity differs")
        for artifact in canonical_manifest.get("repository_artifacts", []):
            raw = artifact.get("path")
            if not isinstance(raw, str):
                raise RunnerError("canonical reconciliation artifact path is invalid")
            path = self.worktree / PurePosixPath(raw)
            if not path.is_file() or sha256_file(path) != artifact.get("sha256"):
                raise RunnerError(f"canonical reconciliation artifact mismatch: {raw}")
        # The Position 24 topology correction supersedes only these live
        # external hashes.  Canonical-reconciliation repository bytes remain
        # immutable historical evidence.
        topology_manifest_path = self.topology_correction_path / "freeze-manifest.json"
        self._verify_sidecar(
            topology_manifest_path,
            self.topology_correction_path / "freeze-manifest.json.sha256",
        )
        topology_manifest = read_json(topology_manifest_path)
        topology_predecessor = (
            topology_manifest.get("predecessor_canonical_reconciliation_correction", {})
            if isinstance(topology_manifest, dict)
            else {}
        )
        if (
            not isinstance(topology_manifest, dict)
            or topology_manifest.get("correction_id") != TOPOLOGY_CORRECTION_ID
            or topology_manifest.get("effective_position") != 24
            or topology_manifest.get("exact_starting_head")
            != "23624624c3a8c764bf597f82caf00595d3f5c5c0"
            or topology_manifest.get("records_published") != 23
            or topology_manifest.get("next_due_position") != 24
            or topology_manifest.get("position_23_unchanged") is not True
            or topology_manifest.get("position_24_scientifically_processed") is not False
            or topology_manifest.get("position_25_unopened") is not True
            or topology_manifest.get("scientific_methodology_changed") is not False
            or topology_manifest.get("reviewer_policy_changed") is not False
            or topology_manifest.get("track_b_modified") is not False
            or topology_manifest.get("superseded_external_runner_artifacts")
            != canonical_manifest.get("external_runner_artifacts")
            or not isinstance(topology_predecessor, dict)
            or topology_predecessor.get("correction_id")
            != CANONICAL_RECONCILIATION_CORRECTION_ID
            or topology_predecessor.get("freeze_manifest_sha256")
            != sha256_file(canonical_manifest_path)
            or topology_predecessor.get("operational_amendment_sha256")
            != sha256_file(
                self.canonical_reconciliation_correction_path
                / "operational-amendment.json"
            )
        ):
            raise RunnerError("Position 24 topology correction identity differs")
        for artifact in topology_manifest.get("repository_artifacts", []):
            raw = artifact.get("path")
            if not isinstance(raw, str):
                raise RunnerError("topology correction artifact path is invalid")
            path = self.worktree / PurePosixPath(raw)
            if not path.is_file() or sha256_file(path) != artifact.get("sha256"):
                raise RunnerError(f"topology correction artifact mismatch: {raw}")
        for artifact in topology_manifest.get("external_runner_artifacts", []):
            path = Path(artifact.get("path", ""))
            if not path.is_file() or sha256_file(path) != artifact.get("sha256"):
                raise RunnerError(f"topology-correction external artifact mismatch: {path}")
        if (
            require_state_binding
            and self.state.get("amendment_manifest_sha256")
            != sha256_file(topology_manifest_path)
        ):
            raise RunnerError("external state does not reference the effective freeze manifest")
        return topology_manifest

    def _reconcile_expected_head(self, snapshot: legacy.Snapshot) -> None:
        expected = self.state["expected_head"]
        actual = snapshot.head
        if expected == actual:
            return
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", expected, actual],
            cwd=self.worktree,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            env=legacy.sanitized_environment(),
        )
        if ancestor.returncode != 0:
            raise RunnerError("external expected_head is not an ancestor of actual HEAD")
        changed = self._git("diff", "--name-only", f"{expected}..{actual}").splitlines()
        due = snapshot.next_due_position
        permitted_prefixes = {
            f"{RUN_RELATIVE_PATH}/positions/{due:08d}/",
            f"{RUN_RELATIVE_PATH}/positions/{max(1, due - 1):08d}/",
        }
        permitted_exact = {
            f"{RUN_RELATIVE_PATH}/records/{max(1, due - 1):08d}.json",
            f"{RUN_RELATIVE_PATH}/ledger.json",
            f"{RUN_RELATIVE_PATH}/ledger.json.sha256",
        }
        if not changed or any(
            path not in permitted_exact
            and not any(path.startswith(prefix) for prefix in permitted_prefixes)
            for path in changed
        ):
            raise RunnerError("valid-descendant HEAD contains unexplained paths")
        classification = DurableClassifier(self).classify(snapshot)
        if classification.state in {
            DurableState.POST_ROLE_RECONCILIATION_REQUIRED,
            DurableState.DETERMINISTIC_INTERFACE_CORRECTION_REQUIRED,
        }:
            raise RunnerError("valid-descendant HEAD has ambiguous durable state")
        self.logger.emit_event(
            EventType.DURABLE_STATE_CLASSIFIED,
            durable_state=DurableState.VALID_DESCENDANT_HEAD_RECONCILIATION.value,
            position=due,
            head=actual,
            reason="actual HEAD is a coherent current-position descendant",
        )
        self._accept_new_head(actual)
        self.logger.emit_event(
            EventType.RECOVERY_REQUIRED,
            recovery_id="VALID_DESCENDANT_HEAD_RECONCILIATION",
            position=due,
            head=actual,
            reason="stale external expected_head reconciled to validated descendant",
        )

    def _validate_worktree_boundary(self, position: int) -> None:
        observed = self._git_status()
        baseline = self.state["baseline_porcelain"]
        extras = [line for line in observed if line not in baseline]
        permitted_prefixes = {
            f"{RUN_RELATIVE_PATH}/positions/{position:08d}/",
            f"{RUN_RELATIVE_PATH}/positions/{max(1, position - 1):08d}/",
        }
        permitted = {
            f"{RUN_RELATIVE_PATH}/records/{position:08d}.json",
            f"{RUN_RELATIVE_PATH}/records/{max(1, position - 1):08d}.json",
            f"{RUN_RELATIVE_PATH}/ledger.json",
            f"{RUN_RELATIVE_PATH}/ledger.json.sha256",
        }
        for line in extras:
            raw = line[3:] if len(line) >= 4 else line
            if raw in permitted or any(raw.startswith(prefix) for prefix in permitted_prefixes):
                continue
            raise RunnerError(f"worktree contains unexplained state: {line}")

    def durable_token(self, position: int) -> legacy.DurableToken:
        return super().durable_token(position)

    def accept_controller_head(
        self, execution: legacy.RoleExecution, before: legacy.DurableToken
    ) -> None:
        actual = self.actual_head()
        if actual == before.head:
            raise RunnerError("controller produced no committed durable transition")
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", before.head, actual],
            cwd=self.worktree,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if ancestor.returncode != 0:
            raise RunnerError("controller HEAD is not a forward descendant")
        changed = self._git("diff", "--name-only", f"{before.head}..{actual}").splitlines()
        self._validate_changed_paths(execution.position, changed)
        self._accept_new_head(actual)
        self._validate_worktree_boundary(execution.position)

    def accept_reviewer(
        self, execution: legacy.RoleExecution, before: legacy.DurableToken
    ) -> None:
        self._accept_reviewer_execution(execution, before)

    def uncommitted_current_paths(
        self, position: int, *, include_previous: bool = False
    ) -> list[Path]:
        baseline = self.state["baseline_porcelain"]
        paths: list[Path] = []
        positions = {position}
        if include_previous and position > 1:
            positions.add(position - 1)
        prefixes = {
            f"{RUN_RELATIVE_PATH}/positions/{item:08d}/" for item in positions
        }
        exact = {
            *(f"{RUN_RELATIVE_PATH}/records/{item:08d}.json" for item in positions),
            f"{RUN_RELATIVE_PATH}/ledger.json",
            f"{RUN_RELATIVE_PATH}/ledger.json.sha256",
        }
        for line in self._git_status():
            if line in baseline:
                continue
            raw = line[3:] if len(line) >= 4 else line
            if raw in exact or any(raw.startswith(prefix) for prefix in prefixes):
                paths.append(self.worktree / raw)
            else:
                raise RunnerError(f"uncommitted transition contains unauthorized path: {raw}")
        return paths

    def _commit_paths(
        self, message: str, paths: Sequence[Path], position: int
    ) -> None:
        before = self.state["expected_head"]
        relatives = [str(path.relative_to(self.worktree)) for path in paths]
        subprocess.run(
            ["git", "add", "--", *relatives],
            cwd=self.worktree,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=legacy.sanitized_environment(),
        )
        commit = subprocess.run(
            ["git", "commit", "-m", message],
            cwd=self.worktree,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=legacy.sanitized_environment(),
        )
        if commit.returncode != 0:
            raise RunnerError(f"interrupted transition commit failed: {commit.stderr.strip()}")
        actual = self.actual_head()
        changed = self._git("diff", "--name-only", f"{before}..{actual}").splitlines()
        self._validate_changed_paths(position, changed)
        self._accept_new_head(actual)
        self._validate_worktree_boundary(position)

    def commit_valid_uncommitted_transition(
        self, position: int, classification: Classification
    ) -> bool:
        paths = self.uncommitted_current_paths(position)
        if not paths:
            return False
        unsafe = {
            DurableState.POST_ROLE_RECONCILIATION_REQUIRED,
            DurableState.DETERMINISTIC_INTERFACE_CORRECTION_REQUIRED,
            DurableState.PARTIAL_PUBLICATION_RECONCILIATION,
            DurableState.POSITION_MATERIALIZATION_REQUIRED,
            DurableState.PRE_POSITION,
        }
        if classification.state in unsafe:
            raise RunnerError(
                f"uncommitted state is not complete enough to commit: {classification.state.value}"
            )
        self._commit_paths(
            f"Reconcile interrupted position {position} {classification.state.value}",
            paths,
            position,
        )
        return True


class DurableClassifier:
    """Metadata-only classifier.  Candidate manifest contents are never opened."""

    METADATA_FILES = frozenset(
        {
            "autonomous-blocker.json",
            "position-authorization.json",
            "hybrid-routing.json",
            "ai-reviewer-a-assignment.json",
            "ai-reviewer-a-decision.json",
            "ai-reviewer-b-assignment.json",
            "ai-reviewer-b-decision.json",
            "combined-review.json",
            "family-feasibility.json",
            "family-construction.json",
            "family-executable-validation.json",
            "admission.json",
        }
    )

    def __init__(self, repository: ProductionRepositoryV2) -> None:
        self.repository = repository

    def _metadata(self, root: Path, name: str) -> dict[str, Any]:
        if name not in self.METADATA_FILES and not re.fullmatch(
            r"ai-reviewer-b-assignment-[0-9]{4}\.json", name
        ):
            raise RunnerError(f"outer runner attempted substantive artifact read: {name}")
        value = read_json(root / name)
        if not isinstance(value, dict):
            raise RunnerError(f"metadata artifact is not an object: {name}")
        return value

    def _due_is_administrative(self, position: int) -> bool:
        source_root = str(self.repository.worktree / "src")
        inserted = source_root not in sys.path
        if inserted:
            sys.path.insert(0, source_root)
        try:
            from cmpilot.candidate_screening_v020 import (  # type: ignore
                QUEUE_RELATIVE_PATH,
                ProtocolInvariantError,
                load_json,
                select_administrative_processing_state,
                verify_sealed_queue_identity,
            )

            verify_sealed_queue_identity(self.repository.worktree)
            queue = load_json(self.repository.worktree / QUEUE_RELATIVE_PATH)
            entries = queue.get("entries")
            if not isinstance(entries, list) or not 1 <= position <= len(entries):
                raise RunnerError("sealed queue due position is unavailable")
            entry = entries[position - 1]
            if not isinstance(entry, Mapping) or entry.get("queue_position") != position:
                raise RunnerError("sealed queue due entry differs")
            state = select_administrative_processing_state(
                entry,
                frozen_repository_anchor_limit=queue.get(
                    "maximum_opened_anchors_per_repository"
                ),
            )
            return state is not None
        except ProtocolInvariantError as error:
            raise RunnerError(f"due queue administrative validation failed: {error}") from error
        finally:
            if inserted:
                sys.path.remove(source_root)

    def classify(self, snapshot: legacy.Snapshot) -> Classification:
        if snapshot.global_action != "CONTINUE":
            return Classification(
                DurableState.GLOBAL_STOP,
                f"replayed global action is {snapshot.global_action}",
                None,
            )
        position = snapshot.next_due_position
        root = self.repository.position_path(position)
        record = self.repository.run_path / "records" / f"{position:08d}.json"
        positions_root = self.repository.run_path / "positions"
        records_root = self.repository.run_path / "records"
        future_positions: set[int] = set()
        if positions_root.is_dir():
            future_positions.update(
                int(path.name)
                for path in positions_root.iterdir()
                if path.name.isdigit()
                and len(path.name) == 8
                and int(path.name) > position
            )
        if records_root.is_dir():
            future_positions.update(
                int(path.stem)
                for path in records_root.glob(
                    "[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].json"
                )
                if int(path.stem) > position
            )
        if future_positions:
            raise RunnerError("future-position isolation violated")
        if record.exists():
            return Classification(
                DurableState.PARTIAL_PUBLICATION_RECONCILIATION,
                "current terminal record exists outside replayed ledger",
                None,
                "INTERRUPTED_TERMINAL_PUBLICATION_RECONCILIATION",
            )
        if not root.exists():
            if self._due_is_administrative(position):
                return Classification(
                    DurableState.ADMINISTRATIVE_TERMINAL,
                    "due sealed queue entry has exact administrative terminal code",
                    legacy.Role.POSITION_CONTROLLER,
                )
            if not self.repository.discovery_materialization_ready():
                return Classification(
                    DurableState.DISCOVERY_ARTIFACT_PROVISIONING_REQUIRED,
                    "frozen discovery transaction required by due materialization is absent",
                    None,
                    "FROZEN_DISCOVERY_ARTIFACT_PROVISIONING",
                )
            return Classification(
                DurableState.PRE_POSITION,
                "due scientific position has no durable directory",
                None,
                "CURRENT_POSITION_MATERIALIZATION",
            )
        if root.is_symlink() or not root.is_dir():
            raise RunnerError("current position path is not a regular directory")
        names = {path.name for path in root.iterdir() if path.is_file()}
        blocker_path = root / "autonomous-blocker.json"
        if blocker_path.exists():
            blocker = self._metadata(root, blocker_path.name)
            digest = sha256_file(blocker_path)
            exact = (
                blocker.get("schema_version") == BLOCKER_SCHEMA
                and blocker.get("blocker_class") == BLOCKER_CLASS
                and blocker.get("stage") == BLOCKER_STAGE
                and blocker.get("queue_position") == position
                and blocker.get("safe_automatic_retry") is False
                and blocker.get("terminal_record_published") is False
            )
            if position == 22:
                exact = exact and digest == BLOCKER_SHA256
            if exact and not {
                "position-authorization.json",
                "candidate-manifest.json",
            } <= names:
                return Classification(
                    DurableState.POSITION_MATERIALIZATION_REQUIRED,
                    "exact immutable missing-materialization-interface blocker",
                    None,
                    "CURRENT_POSITION_MATERIALIZATION",
                )
            if blocker.get("blocker_class") == "DISCOVERY_ARTIFACT_PROVISIONING_REQUIRED":
                return Classification(
                    DurableState.DISCOVERY_ARTIFACT_PROVISIONING_REQUIRED,
                    "registered frozen discovery copy is absent",
                    None,
                    "FROZEN_DISCOVERY_ARTIFACT_PROVISIONING",
                )
            if not exact:
                raise RunnerError("unknown or conflicting durable blocker")
        authorization = "position-authorization.json" in names
        manifest = "candidate-manifest.json" in names
        if authorization != manifest:
            return Classification(
                DurableState.DETERMINISTIC_INTERFACE_CORRECTION_REQUIRED,
                "partial authorization/manifest write requires exact reconstruction",
                None,
                "CURRENT_POSITION_MATERIALIZATION",
            )
        if not authorization:
            if names <= {"autonomous-blocker.json"}:
                return Classification(
                    DurableState.POSITION_MATERIALIZATION_REQUIRED,
                    "current directory is empty except for exact historical blocker",
                    None,
                    "CURRENT_POSITION_MATERIALIZATION",
                )
            raise RunnerError("unknown pre-materialization position state")
        self.repository.validate_materialized_position(position)
        auth = self._metadata(root, "position-authorization.json")
        if (
            auth.get("schema") != "candidate-screening-position-authorization-v0.2.0"
            or auth.get("queue_position") != position
            or auth.get(f"position_{position + 1}_authorized") is not False
        ):
            raise RunnerError("position authorization metadata differs")
        tptm_names = {
            "tptm-run-envelope.json",
            "tptm-result.json",
            "hybrid-routing.json",
        }
        present_tptm = tptm_names & names
        if not present_tptm:
            state = (
                DurableState.TPTM_REQUIRED
                if "position-materialization-recovery.json" in names
                else DurableState.POSITION_MATERIALIZED
            )
            return Classification(
                state,
                "authorization and manifest exist; TPTM has not run",
                legacy.Role.POSITION_CONTROLLER,
            )
        if present_tptm != tptm_names:
            return Classification(
                DurableState.POST_ROLE_RECONCILIATION_REQUIRED,
                "partial TPTM durable triple",
                legacy.Role.POSITION_CONTROLLER,
            )
        self.repository.validate_tptm_bundle(position)
        routing = self._metadata(root, "hybrid-routing.json")
        if routing.get("queue_position") != position:
            raise RunnerError("hybrid routing position binding differs")
        route = routing.get("state")
        if route == "AUTO_MECHANICAL_REJECT":
            return Classification(
                DurableState.AUTO_MECHANICAL_TERMINAL,
                "frozen routing selected automatic mechanical rejection",
                legacy.Role.POSITION_CONTROLLER,
            )
        if route == "OUT_OF_SCOPE_UNSUPPORTED":
            return Classification(
                DurableState.OUT_OF_SCOPE_TERMINAL,
                "frozen routing selected unsupported terminal",
                legacy.Role.POSITION_CONTROLLER,
            )
        if route == "ANALYSIS_ERROR":
            raise RunnerError("TPTM analysis error is a fail-closed scientific blocker")
        if route not in {"STRUCTURED_REVIEW_REQUIRED", "AUTO_RETAIN_FOR_CONSTRUCTION"}:
            raise RunnerError(f"unknown hybrid routing state: {route}")
        assignment_a = root / "ai-reviewer-a-assignment.json"
        decision_a = root / "ai-reviewer-a-decision.json"
        if route == "STRUCTURED_REVIEW_REQUIRED" and "review-packet.json" in names:
            self.repository.validate_review_packet(position)
        if route == "STRUCTURED_REVIEW_REQUIRED" and not assignment_a.exists():
            if "review-packet.json" not in names:
                return Classification(
                    DurableState.POST_ROLE_RECONCILIATION_REQUIRED,
                    "structured route lacks durable review packet",
                    legacy.Role.POSITION_CONTROLLER,
                )
            return Classification(
                DurableState.STRUCTURED_REVIEW_REQUIRED,
                "bounded AI-A assignment must be materialized",
                legacy.Role.POSITION_CONTROLLER,
            )
        if route == "AUTO_RETAIN_FOR_CONSTRUCTION" and not assignment_a.exists():
            return self._classify_family(root, names, None)
        if not assignment_a.exists():
            raise RunnerError("structured review state lacks AI-A assignment")
        try:
            self.repository.validate_assignment(assignment_a, legacy.Role.AI_FIRST_REVIEW)
        except legacy.RunnerError as error:
            raise RunnerError(f"AI-A assignment invalid: {error}") from error
        if not decision_a.exists():
            return Classification(
                DurableState.AI_FIRST_REVIEW_REQUIRED,
                "validated bounded AI-A assignment awaits fresh review",
                legacy.Role.AI_FIRST_REVIEW,
            )
        authoritative_a = self.repository.validate_ai_decision(
            decision_a, legacy.Role.AI_FIRST_REVIEW
        )
        assignment_b = self.repository.latest_b_assignment(position)
        decision_b = root / "ai-reviewer-b-decision.json"
        if assignment_b is None:
            required, reason, _bucket = self.repository.reviewer_b_requirement(position)
            if required:
                return Classification(
                    DurableState.AI_SECOND_ASSIGNMENT_REQUIRED,
                    f"frozen Reviewer-B trigger is true: {reason}",
                    legacy.Role.CONTINUATION_CONTROLLER,
                )
            if decision_b.exists():
                raise RunnerError("AI-B decision exists without triggered assignment")
            if "family-feasibility.json" in names or "combined-review.json" in names:
                combined: Mapping[str, Any]
                if "combined-review.json" in names:
                    raise RunnerError("A-only route cannot fabricate a two-review combination")
                combined = {
                    "combined_outcome": authoritative_a["semantic_decision"]["outcome"],
                    "authorized_next_action": (
                        "CONSTRAINED_FAMILY_FEASIBILITY_INVESTIGATION"
                        if authoritative_a["semantic_decision"]["outcome"]
                        == "REVIEW_UNRESOLVED"
                        else "CONSTRAINED_FAMILY_CONSTRUCTION"
                    ),
                }
                return self._classify_family(root, names, combined)
            return Classification(
                DurableState.AI_SECOND_NOT_REQUIRED,
                f"frozen Reviewer-B trigger is false: {reason}",
                legacy.Role.CONTINUATION_CONTROLLER,
            )
        try:
            self.repository.validate_assignment(assignment_b, legacy.Role.AI_SECOND_REVIEW)
        except legacy.RunnerError as error:
            if decision_b.exists():
                raise RunnerError("invalid B assignment already has a B decision")
            if not self.repository.b_assignment_completion_permitted(
                assignment_b, position
            ):
                raise RunnerError(
                    f"invalid blinded B assignment is not mechanically correctable: {error}"
                ) from error
            return Classification(
                DurableState.REVIEWER_B_ASSIGNMENT_COMPLETION_REQUIRED,
                "triggered B assignment needs registered append-only completion",
                None,
                "REVIEWER_B_ASSIGNMENT_COMPLETION",
            )
        if not decision_b.exists():
            return Classification(
                DurableState.AI_SECOND_REVIEW_REQUIRED,
                "validated blinded AI-B assignment awaits fresh review",
                legacy.Role.AI_SECOND_REVIEW,
            )
        self.repository.validate_ai_decision(decision_b, legacy.Role.AI_SECOND_REVIEW)
        if "combined-review.json" not in names:
            return Classification(
                DurableState.COMBINATION_REQUIRED,
                "both authoritative decisions await exact frozen combination",
                legacy.Role.COMBINATION_CONTINUATION_CONTROLLER,
            )
        combined = self.repository.validate_combined_review(
            position, root / "combined-review.json"
        )
        return self._classify_family(root, names, combined)

    def _classify_family(
        self,
        root: Path,
        names: set[str],
        combined: Mapping[str, Any] | None,
    ) -> Classification:
        outcome = None if combined is None else combined.get("combined_outcome")
        next_action = None if combined is None else combined.get("authorized_next_action")
        if "family-feasibility.json" not in names:
            if outcome == "REVIEW_REJECT":
                return Classification(
                    DurableState.REVIEW_REJECT,
                    "authoritative combined review rejects",
                    legacy.Role.COMBINATION_CONTINUATION_CONTROLLER,
                )
            if outcome == "REVIEW_RETAIN" or combined is None:
                return Classification(
                    DurableState.CONSTRUCTION_REQUIRED,
                    "retained candidate requires frozen family construction",
                    legacy.Role.COMBINATION_CONTINUATION_CONTROLLER,
                )
            if outcome == "REVIEW_UNRESOLVED" and next_action == (
                "CONSTRAINED_FAMILY_FEASIBILITY_INVESTIGATION"
            ):
                return Classification(
                    DurableState.CONSTRAINED_FAMILY_FEASIBILITY_REQUIRED,
                    "frozen disagreement policy requires constrained feasibility",
                    legacy.Role.COMBINATION_CONTINUATION_CONTROLLER,
                )
            if outcome == "REVIEW_UNRESOLVED":
                return Classification(
                    DurableState.REVIEW_UNRESOLVED,
                    "combined review is unresolved",
                    legacy.Role.COMBINATION_CONTINUATION_CONTROLLER,
                )
            raise RunnerError("combined review outcome is unknown")
        family = self.repository.validate_family_metadata(
            int(root.name), root / "family-feasibility.json", combined
        )
        if family.get("reason_code") == (
            "NO_UNIQUE_FOCAL_HYPOTHESIS_UNDER_FROZEN_DISAGREEMENT_POLICY"
        ):
            return Classification(
                DurableState.NO_UNIQUE_FOCAL_FAILURE,
                "frozen disagreement policy found no unique focal hypothesis",
                legacy.Role.COMBINATION_CONTINUATION_CONTROLLER,
            )
        construction = family.get("family_construction_state")
        if construction == "FAILED":
            return Classification(
                DurableState.CONSTRUCTION_FAILED,
                "family construction failed",
                legacy.Role.COMBINATION_CONTINUATION_CONTROLLER,
            )
        if construction not in {"SUCCEEDED", "CONSTRUCTED", "READY", "COMPLETED"}:
            if "family-executable-validation.json" in names:
                raise RunnerError(
                    "executable validation exists before successful construction"
                )
            return Classification(
                DurableState.CONSTRUCTION_REQUIRED,
                "family feasibility is recorded; construction remains incomplete",
                legacy.Role.COMBINATION_CONTINUATION_CONTROLLER,
            )
        executable_path = root / "family-executable-validation.json"
        if not executable_path.is_file():
            return Classification(
                DurableState.EXECUTABLE_VALIDATION_REQUIRED,
                "constructed family awaits executable validation",
                legacy.Role.COMBINATION_CONTINUATION_CONTROLLER,
            )
        executable = self.repository.validate_executable_metadata(
            int(root.name), executable_path, family
        )
        if executable.get("validation_state") == "FAILED":
            return Classification(
                DurableState.EXECUTABLE_VALIDATION_FAILED,
                "authoritative executable validation failed",
                legacy.Role.COMBINATION_CONTINUATION_CONTROLLER,
            )
        if executable.get("validation_state") == "PASSED":
            return Classification(
                DurableState.FINAL_READY,
                "executable evidence is valid and admission/publication is pending",
                legacy.Role.COMBINATION_CONTINUATION_CONTROLLER,
            )
        raise RunnerError("family executable-validation state is unknown")


STATE_ROLE_HANDLERS: dict[DurableState, legacy.Role | None] = {
    state: None for state in DurableState
}
STATE_ROLE_HANDLERS.update(
    {
        DurableState.ADMINISTRATIVE_TERMINAL: legacy.Role.POSITION_CONTROLLER,
        DurableState.POSITION_MATERIALIZED: legacy.Role.POSITION_CONTROLLER,
        DurableState.TPTM_REQUIRED: legacy.Role.POSITION_CONTROLLER,
        DurableState.AUTO_MECHANICAL_TERMINAL: legacy.Role.POSITION_CONTROLLER,
        DurableState.OUT_OF_SCOPE_TERMINAL: legacy.Role.POSITION_CONTROLLER,
        DurableState.STRUCTURED_REVIEW_REQUIRED: legacy.Role.POSITION_CONTROLLER,
        DurableState.AI_FIRST_ASSIGNMENT_READY: legacy.Role.AI_FIRST_REVIEW,
        DurableState.AI_FIRST_REVIEW_REQUIRED: legacy.Role.AI_FIRST_REVIEW,
        DurableState.AI_FIRST_DECISION_READY: legacy.Role.CONTINUATION_CONTROLLER,
        DurableState.CONTINUATION_AFTER_A: legacy.Role.CONTINUATION_CONTROLLER,
        DurableState.AI_SECOND_NOT_REQUIRED: legacy.Role.CONTINUATION_CONTROLLER,
        DurableState.AI_SECOND_ASSIGNMENT_REQUIRED: legacy.Role.CONTINUATION_CONTROLLER,
        DurableState.AI_SECOND_ASSIGNMENT_CORRECTION_REQUIRED: None,
        DurableState.REVIEWER_B_ASSIGNMENT_COMPLETION_REQUIRED: None,
        DurableState.AI_SECOND_REVIEW_REQUIRED: legacy.Role.AI_SECOND_REVIEW,
        DurableState.AI_SECOND_DECISION_READY: (
            legacy.Role.COMBINATION_CONTINUATION_CONTROLLER
        ),
        DurableState.COMBINATION_REQUIRED: (
            legacy.Role.COMBINATION_CONTINUATION_CONTROLLER
        ),
        DurableState.REVIEW_REJECT: legacy.Role.COMBINATION_CONTINUATION_CONTROLLER,
        DurableState.REVIEW_RETAIN: legacy.Role.COMBINATION_CONTINUATION_CONTROLLER,
        DurableState.REVIEW_UNRESOLVED: legacy.Role.COMBINATION_CONTINUATION_CONTROLLER,
        DurableState.CONSTRAINED_FAMILY_FEASIBILITY_REQUIRED: (
            legacy.Role.COMBINATION_CONTINUATION_CONTROLLER
        ),
        DurableState.NO_UNIQUE_FOCAL_FAILURE: (
            legacy.Role.COMBINATION_CONTINUATION_CONTROLLER
        ),
        DurableState.CONSTRUCTION_REQUIRED: (
            legacy.Role.COMBINATION_CONTINUATION_CONTROLLER
        ),
        DurableState.CONSTRUCTION_FAILED: (
            legacy.Role.COMBINATION_CONTINUATION_CONTROLLER
        ),
        DurableState.FAMILY_READY: legacy.Role.COMBINATION_CONTINUATION_CONTROLLER,
        DurableState.EXECUTABLE_VALIDATION_REQUIRED: (
            legacy.Role.COMBINATION_CONTINUATION_CONTROLLER
        ),
        DurableState.EXECUTABLE_VALIDATION_FAILED: (
            legacy.Role.COMBINATION_CONTINUATION_CONTROLLER
        ),
        DurableState.FINAL_READY: legacy.Role.COMBINATION_CONTINUATION_CONTROLLER,
        DurableState.TERMINAL_PUBLICATION_PENDING: (
            legacy.Role.COMBINATION_CONTINUATION_CONTROLLER
        ),
        DurableState.POST_ROLE_RECONCILIATION_REQUIRED: legacy.Role.POSITION_CONTROLLER,
        DurableState.VALID_DESCENDANT_HEAD_RECONCILIATION: None,
    }
)


RECOVERY_HANDLERS = {
    "CURRENT_POSITION_MATERIALIZATION",
    "FROZEN_DISCOVERY_ARTIFACT_PROVISIONING",
    "REVIEWER_B_ASSIGNMENT_COMPLETION",
    "INTERRUPTED_TERMINAL_PUBLICATION_RECONCILIATION",
    "VALID_DESCENDANT_HEAD_RECONCILIATION",
}


class CodexRoleExecutorV2(legacy.CodexRoleExecutor):
    def __init__(self, *args: Any, heartbeat: Heartbeat, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.heartbeat = heartbeat

    def execute(
        self, role: legacy.Role, position: int, expected_head: str
    ) -> legacy.RoleExecution:
        if role in {legacy.Role.AI_FIRST_REVIEW, legacy.Role.AI_SECOND_REVIEW}:
            same_boundary = (
                self.heartbeat.network_retry_role == role.value
                and self.heartbeat.network_retry_position == position
            )
            attempt = self.heartbeat.review_attempt + 1 if same_boundary else 1
            retry_count = self.heartbeat.network_retry_count if same_boundary else 0
            self.heartbeat.set_role(role.value, None)
            self.heartbeat.set_review_attempt(
                attempt,
                retry_count,
                role=role.value,
                position=position,
            )
        return super().execute(role, position, expected_head)

    def _probe_reviewer_network(
        self, role: legacy.Role
    ) -> review_network.SandboxNetworkProbe:
        return review_network.probe_reviewer_sandbox_network(
            runner_root=self.repository.runner_root,
            role=role.value,
            environment=legacy.sanitized_environment(),
        )

    def _execute_isolated_reviewer(
        self,
        role: legacy.Role,
        position: int,
        prompt: str,
        prompt_digest: str,
        invocation_id: str,
        started: str,
        role_dir: Path,
        assignment_path: Path | None,
        assignment: Mapping[str, Any] | None,
    ) -> legacy.RoleExecution:
        # The exact same schema/profile check runs for A and blinded B before
        # network probing, capsule construction, or child-process launch.
        try:
            if assignment is None:
                self.verify_reviewer_output_schema(role)
            else:
                self.verify_reviewer_output_schema(role, assignment)
        except legacy.ProviderEvidenceReferenceContractError as error:
            raise ProviderEvidenceReferenceContractIncompatible(str(error)) from error
        except legacy.RunnerError as error:
            raise ProviderOutputSchemaIncompatible(str(error)) from error
        wait_for_reviewer_network(
            role=role,
            position=position,
            probe=lambda: self._probe_reviewer_network(role),
            heartbeat=self.heartbeat,
            logger=self.logger,
        )
        return super()._execute_isolated_reviewer(
            role,
            position,
            prompt,
            prompt_digest,
            invocation_id,
            started,
            role_dir,
            assignment_path,
            assignment,
        )

    def render_prompt(
        self,
        role: legacy.Role,
        position: int,
        expected_head: str,
        *,
        assignment_path: Path | None = None,
        assignment: Mapping[str, Any] | None = None,
    ) -> str:
        prompt = super().render_prompt(
            role,
            position,
            expected_head,
            assignment_path=assignment_path,
            assignment=assignment,
        )
        if role in {
            legacy.Role.CONTINUATION_CONTROLLER,
            legacy.Role.COMBINATION_CONTINUATION_CONTROLLER,
        }:
            executable_overlay = (
                "\nDURABLE EXECUTABLE-AUTHORITY OVERLAY "
                "(durable-autonomous-orchestration-v0.1):\n"
                "Before any FAMILY_VALIDATION_FAILED, ADMIT_FINAL, or validated-"
                "but-not-admitted publication, create and validate "
                "family-executable-validation.json against "
                "benchmark-selection/screening/operational-amendments/"
                "durable-autonomous-orchestration-v0.1/"
                "family-executable-validation.schema.json. Its canonical self-hash "
                "excludes executable_validation_sha256. PASSED is lawful only for "
                "p*(S)=TRUE, p*(C)=TRUE, p*(I)=FALSE and the frozen oracle, witness, "
                "single-focal-change, category, and repository-independence conditions.\n"
            )
            prompt += executable_overlay
        if role is not legacy.Role.POSITION_CONTROLLER:
            return prompt
        overlay = (
            "\nDURABLE RECONCILER OVERLAY (frozen by durable-autonomous-orchestration-v0.1):\n"
            "Repository durable state is authoritative; runner/model prose is not.\n"
            "If position-authorization.json and candidate-manifest.json already exist, "
            "validate them and continue immediately AFTER materialization. Do not recreate "
            "or rewrite autonomous-blocker.json and do not repeat the preflight that created it.\n"
            "Commit exactly one valid current-position transition. Never inspect or open the "
            "next or later queue entry.\n"
        )
        return prompt + overlay

    def _run_process(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        role: legacy.Role,
        position: int,
        prompt: str,
        prompt_digest: str,
        invocation_id: str,
        started: str,
        role_dir: Path,
        last_message_path: Path | None,
    ) -> legacy.RoleExecution:
        if "resume" in command or "fork" in command:
            raise RunnerError("resume/fork is prohibited across logical roles")
        stdout_path = role_dir / "stdout.jsonl"
        stderr_path = role_dir / "stderr.txt"
        reviewer_role = role in {
            legacy.Role.AI_FIRST_REVIEW,
            legacy.Role.AI_SECOND_REVIEW,
        }
        stall_threshold = float(
            getattr(self, "network_stall_seconds", CODEX_NETWORK_STALL_SECONDS)
        )
        poll_interval = float(getattr(self, "process_poll_interval_seconds", 0.5))
        detector = (
            NetworkStallDetector(time.monotonic(), stall_threshold)
            if reviewer_role
            else None
        )
        offsets = {stdout_path: 0, stderr_path: 0}
        infrastructure_failure: str | None = None
        partial_decision_present = False
        failure_since_utc: str | None = None
        with stdout_path.open("xb") as stdout_stream, stderr_path.open("xb") as stderr_stream:
            try:
                process = subprocess.Popen(
                    list(command),
                    cwd=cwd,
                    stdin=subprocess.PIPE,
                    stdout=stdout_stream,
                    stderr=stderr_stream,
                    text=True,
                    env=legacy.sanitized_environment(),
                    start_new_session=True,
                )
            except OSError as error:
                attempted = Path(command[0]) if command else self.codex_bin
                raise RunnerError(
                    _codex_diagnostic(
                        attempted,
                        exists=attempted.exists(),
                        regular=attempted.is_file(),
                        executable=os.access(attempted, os.X_OK),
                        version_check_status="PASS_AT_PRE_RUN_PREFLIGHT",
                        os_error=f"{type(error).__name__}: {error}",
                    )
                ) from error
            try:
                self.heartbeat.set_role(role.value, process.pid)
                if process.stdin is None:
                    raise RunnerError("Codex child stdin is unavailable")
                try:
                    process.stdin.write(prompt)
                    process.stdin.close()
                except BrokenPipeError:
                    pass
                while process.poll() is None:
                    self.heartbeat.write(status="RUNNING")
                    if detector is not None:
                        failure_before = detector.network_failure_since
                        for output_path in (stdout_path, stderr_path):
                            delta, offsets[output_path] = _read_output_delta(
                                output_path, offsets[output_path]
                            )
                            detector.observe(delta, time.monotonic())
                        if (
                            failure_before is None
                            and detector.network_failure_since is not None
                        ):
                            failure_since_utc = utc_now()
                            self.heartbeat.set_network_state(
                                "RECONNECTING",
                                failure_since=failure_since_utc,
                                reason="Codex emitted network transport failures",
                            )
                        elif (
                            failure_before is not None
                            and detector.network_failure_since is None
                        ):
                            failure_since_utc = None
                            self.heartbeat.set_network_state(
                                "CONNECTED",
                                failure_since=None,
                                reason="Codex resumed substantive progress",
                            )
                        now = time.monotonic()
                        if detector.stalled(now):
                            decision_name = (
                                "ai-reviewer-a-decision.json"
                                if role is legacy.Role.AI_FIRST_REVIEW
                                else "ai-reviewer-b-decision.json"
                            )
                            canonical_decision = self.repository.position_path(
                                position
                            ) / decision_name
                            if not canonical_decision.exists():
                                partial_decision_present = bool(
                                    last_message_path is not None
                                    and last_message_path.is_file()
                                    and last_message_path.stat().st_size > 0
                                )
                                infrastructure_failure = "CODEX_NETWORK_STALL"
                                stalled_seconds = int(
                                    now - (detector.network_failure_since or now)
                                )
                                self.heartbeat.set_network_state(
                                    "STALLED",
                                    wait_seconds=stalled_seconds,
                                    failure_since=failure_since_utc,
                                    reason="CODEX_NETWORK_STALL",
                                )
                                self.logger.emit_event(
                                    EventType.CODEX_NETWORK_STALL,
                                    position=position,
                                    role=role.value,
                                    child_pid=process.pid,
                                    network_state="STALLED",
                                    network_failure_since=failure_since_utc,
                                    reconnect_only_seconds=stalled_seconds,
                                    partial_decision_present=partial_decision_present,
                                    reason=(
                                        "continuous reconnect-only transport failure "
                                        "without substantive progress"
                                    ),
                                )
                                _terminate_process_group(process)
                                break
                    time.sleep(poll_interval)
                exit_code = process.returncode
            except BaseException:
                _terminate_process_group(process)
                raise
            finally:
                self.heartbeat.set_role(None, None)
        stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
        stderr = stderr_path.read_text(encoding="utf-8", errors="replace")
        if reviewer_role and is_invalid_provider_schema_failure(stdout, stderr):
            infrastructure_failure = INVALID_PROVIDER_SCHEMA_FAILURE
        thread_id, observed_model = legacy.parse_codex_jsonl(stdout)
        return legacy.RoleExecution(
            role=role,
            position=position,
            invocation_id=invocation_id,
            started_at_utc=started,
            ended_at_utc=utc_now(),
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            prompt=prompt,
            prompt_sha256=prompt_digest,
            codex_thread_id=thread_id,
            model_identifier=observed_model or self.model or "CLI_DEFAULT_SELECTOR",
            profile_identifier=self.profile,
            last_message_path=last_message_path,
            infrastructure_failure=infrastructure_failure,
            partial_decision_present=partial_decision_present,
        )


class RecoveryEngine:
    def __init__(
        self,
        repository: ProductionRepositoryV2,
        logger: StructuredLogger,
        heartbeat: Heartbeat,
    ) -> None:
        self.repository = repository
        self.logger = logger
        self.heartbeat = heartbeat

    def run(self, classification: Classification, position: int) -> None:
        recovery_id = classification.recovery_id
        if recovery_id not in RECOVERY_HANDLERS:
            raise RunnerError(f"unknown repair requirement: {recovery_id}")
        self.logger.emit_event(
            EventType.RECOVERY_REQUIRED,
            recovery_id=recovery_id,
            durable_state=classification.state.value,
            position=position,
            role="DETERMINISTIC_RECOVERY",
            reason=classification.reason,
        )
        if recovery_id == "CURRENT_POSITION_MATERIALIZATION":
            self._materialize(position)
        elif recovery_id == "REVIEWER_B_ASSIGNMENT_COMPLETION":
            self._complete_b_assignment(position)
        elif recovery_id == "INTERRUPTED_TERMINAL_PUBLICATION_RECONCILIATION":
            self._reconcile_publication(position)
        elif recovery_id == "FROZEN_DISCOVERY_ARTIFACT_PROVISIONING":
            self._provision_discovery(position)
        else:
            # Valid-descendant reconciliation occurs during repository preflight.
            return

    def _commit(self, message: str, paths: Sequence[Path], position: int) -> None:
        self.repository._commit_paths(message, paths, position)

    def _materialize(self, position: int) -> None:
        # Repeat the same read-only reachable-recovery validation immediately
        # before the write-capable interface.  The interface itself performs
        # the same validation before creating any position output.
        run_current_materialization_preflight(self.repository, position)
        root = self.repository.position_path(position)
        blocker = root / "autonomous-blocker.json"
        blocker_before = blocker.read_bytes() if blocker.exists() else None
        ledger_before = sha256_file(self.repository.ledger_path)
        records_before = self.repository.snapshot().records_published
        recovery_dir = (
            self.logger.run_dir / f"position-{position:08d}" / "materialization-recovery"
        )
        recovery_dir.mkdir(parents=True, exist_ok=True)
        command = [
            sys.executable,
            str(self.repository.worktree / MATERIALIZER_RELATIVE_PATH),
            "--repository-root",
            str(self.repository.worktree),
            "--expected-position",
            str(position),
        ]
        process = subprocess.run(
            command,
            cwd=self.repository.worktree,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            env=legacy.sanitized_environment(),
        )
        legacy.write_exclusive(
            recovery_dir / "stdout.json", process.stdout.encode("utf-8"), mode=0o600
        )
        legacy.write_exclusive(
            recovery_dir / "stderr.txt", process.stderr.encode("utf-8"), mode=0o600
        )
        if process.returncode != 0:
            raise RunnerError(
                "current-position materializer failed: "
                + (process.stderr.strip() or process.stdout.strip())
            )
        if blocker_before is not None and blocker.read_bytes() != blocker_before:
            raise RunnerError("materialization recovery changed historical blocker bytes")
        if sha256_file(self.repository.ledger_path) != ledger_before:
            raise RunnerError("materialization recovery changed ledger")
        if self.repository._snapshot_at_actual_head().records_published != records_before:
            raise RunnerError("materialization recovery published a terminal record")
        outputs = [
            root / "position-authorization.json",
            root / "candidate-manifest.json",
        ]
        receipt = root / "position-materialization-recovery.json"
        if blocker_before is not None:
            outputs.append(receipt)
        if any(not path.is_file() for path in outputs):
            raise RunnerError("materialization recovery outputs are incomplete")
        self._commit(
            f"Materialize due position {position} through frozen deterministic interface",
            outputs,
            position,
        )

    def _complete_b_assignment(self, position: int) -> None:
        root = self.repository.position_path(position)
        if (root / "ai-reviewer-b-decision.json").exists():
            raise RunnerError("cannot correct B assignment after B decision")
        base = self.repository.latest_b_assignment(position)
        if base is None or not base.is_file():
            raise RunnerError("base B assignment is absent")
        if not self.repository.b_assignment_completion_permitted(base, position):
            raise RunnerError("B assignment is not eligible for mechanical completion")
        value = read_json(base)
        assignment_a = self.repository.validate_assignment(
            root / "ai-reviewer-a-assignment.json", legacy.Role.AI_FIRST_REVIEW
        )
        if not isinstance(value, dict):
            raise RunnerError("base B assignment is invalid")
        completed = dict(value)
        for key in (
            "candidate_id",
            "review_packet",
            "permitted_evidence_paths",
            "permitted_evidence_sha256",
            "permitted_interface_paths",
            "permitted_interface_sha256",
        ):
            completed[key] = assignment_a[key]
        serialized = json.dumps(completed, sort_keys=True).lower()
        if any(fragment in serialized for fragment in legacy.FORBIDDEN_B_PATH_FRAGMENTS):
            # Reviewer-role labels legitimately contain reviewer-a only in neither
            # copied paths nor prohibited boundary; paths are the relevant surface.
            paths = completed.get("permitted_evidence_paths", []) + completed.get(
                "permitted_interface_paths", []
            )
            if any(
                fragment in "\n".join(paths).lower()
                for fragment in legacy.FORBIDDEN_B_PATH_FRAGMENTS
            ):
                raise RunnerError("B assignment correction would violate blinding")
        # The unnumbered assignment is generation 1; append-only completion starts
        # at 0002, matching the already-frozen historical mechanism.
        existing = [1]
        for path in root.glob("ai-reviewer-b-assignment-[0-9][0-9][0-9][0-9].json"):
            existing.append(int(path.stem.rsplit("-", 1)[1]))
        output = root / f"ai-reviewer-b-assignment-{max(existing) + 1:04d}.json"
        if output.exists():
            raise RunnerError("next append-only B assignment generation already exists")
        temporary = root / f".{output.name}.{uuid.uuid4().hex}.tmp"
        try:
            legacy.write_exclusive(
                temporary, legacy.canonical_json_bytes(completed), mode=0o644
            )
            self.repository.validate_assignment(
                temporary, legacy.Role.AI_SECOND_REVIEW
            )
            try:
                os.link(temporary, output)
            except FileExistsError as error:
                raise RunnerError(
                    "next append-only B assignment generation appeared concurrently"
                ) from error
        finally:
            temporary.unlink(missing_ok=True)
        self._commit(
            f"Complete position {position} blinded Reviewer B assignment append-only",
            [output],
            position,
        )

    def _provision_discovery(self, position: int) -> None:
        plan = read_json(DISCOVERY_RECOVERY_PLAN_PATH)
        plan_keys = {
            "schema",
            "classification",
            "candidate_content_parsed",
            "network_accessed",
            "records",
            "scientific_methodology_changed",
        }
        row_keys = {
            "id",
            "source_checkout",
            "transaction_relative_path",
            "expected_tree_sha256",
            "expected_file_count",
            "expected_total_bytes",
            "evidence_record_relative_path",
            "evidence_record_sha256",
        }
        if (
            not isinstance(plan, dict)
            or set(plan) != plan_keys
            or plan.get("schema") != "track-a-frozen-discovery-recovery-plan-v0.1"
            or plan.get("classification")
            != "HASH_VERIFIED_COPY_ONLY_CANONICAL_DISCOVERY_PROVISIONING"
            or plan.get("candidate_content_parsed") is not False
            or plan.get("network_accessed") is not False
            or plan.get("scientific_methodology_changed") is not False
            or not isinstance(plan.get("records"), list)
            or len(plan["records"]) != 2
            or {
                row.get("id") for row in plan["records"] if isinstance(row, dict)
            }
            != {"FAILED_PARENT", "SUCCESSFUL_RESUME"}
        ):
            raise RunnerError("frozen discovery recovery plan identity differs")
        output_root = self.repository.worktree / (
            "benchmark-selection/screening/provisioning/"
            "autonomous-recovery-v0.1"
        )
        for row in plan["records"]:
            if not isinstance(row, dict) or set(row) != row_keys:
                raise RunnerError("discovery recovery plan row is invalid")
            source_checkout = Path(row["source_checkout"])
            relative = PurePosixPath(row["transaction_relative_path"])
            evidence_relative = PurePosixPath(row["evidence_record_relative_path"])
            if (
                not source_checkout.is_absolute()
                or relative.is_absolute()
                or not relative.parts
                or ".." in relative.parts
                or evidence_relative.is_absolute()
                or not evidence_relative.parts
                or ".." in evidence_relative.parts
            ):
                raise RunnerError("discovery recovery plan path escapes its authority")
            source = source_checkout / relative
            destination = self.repository.worktree / relative
            evidence = self.repository.worktree / evidence_relative
            if sha256_file(evidence) != row["evidence_record_sha256"]:
                raise RunnerError("discovery provisioning evidence record differs")
            evidence_value = read_json(evidence)
            if (
                not isinstance(evidence_value, dict)
                or evidence_value.get("source_checkout") != str(source_checkout)
                or evidence_value.get("source_transaction_logical_path") != str(relative)
                or evidence_value.get("destination_transaction_logical_path")
                != str(relative)
                or evidence_value.get("source_tree_sha256")
                != row["expected_tree_sha256"]
                or evidence_value.get("file_count") != row["expected_file_count"]
                or evidence_value.get("total_bytes") != row["expected_total_bytes"]
                or evidence_value.get("candidate_content_parsed") is not False
                or evidence_value.get("network_accessed") is not False
            ):
                raise RunnerError("discovery provisioning evidence semantics differ")
            if destination.exists():
                command = [
                    sys.executable,
                    str(
                        self.repository.worktree
                        / "scripts/provision_frozen_discovery_artifacts.py"
                    ),
                    "verify",
                    "--source",
                    str(source),
                    "--destination",
                    str(destination),
                ]
            else:
                identifier = row["id"].lower().replace("_", "-")
                outputs = {
                    "source": output_root / f"{identifier}-source-fingerprint.json",
                    "destination": output_root
                    / f"{identifier}-destination-fingerprint.json",
                    "provenance": output_root / f"{identifier}-provisioning-record.json",
                }
                if any(path.exists() for path in outputs.values()):
                    raise RunnerError("partial discovery provisioning recovery exists")
                output_root.mkdir(parents=True, exist_ok=True)
                command = [
                    sys.executable,
                    str(
                        self.repository.worktree
                        / "scripts/provision_frozen_discovery_artifacts.py"
                    ),
                    "provision",
                    "--source",
                    str(source),
                    "--destination",
                    str(destination),
                    "--source-manifest",
                    str(outputs["source"]),
                    "--destination-manifest",
                    str(outputs["destination"]),
                    "--provenance",
                    str(outputs["provenance"]),
                    "--source-checkout",
                    str(source_checkout),
                    "--source-logical-path",
                    str(relative),
                    "--destination-worktree",
                    str(self.repository.worktree),
                    "--destination-logical-path",
                    str(relative),
                    "--tool-commit",
                    str(evidence_value["provisioning_tool_commit"]),
                    "--timestamp-utc",
                    utc_now(),
                ]
            completed = subprocess.run(
                command,
                cwd=self.repository.worktree,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                env=legacy.sanitized_environment(),
            )
            try:
                result = json.loads(completed.stdout)
            except json.JSONDecodeError as error:
                raise RunnerError("discovery provisioning output is invalid") from error
            if (
                completed.returncode != 0
                or result.get("pass") is not True
                or result.get("source_tree_sha256") != row["expected_tree_sha256"]
                or result.get("destination_tree_sha256") != row["expected_tree_sha256"]
                or result.get("file_count") != row["expected_file_count"]
                or result.get("total_bytes") != row["expected_total_bytes"]
                or result.get("network_accessed") is not False
            ):
                raise RunnerError("frozen discovery provisioning validation failed")
        if not self.repository.discovery_materialization_ready():
            raise RunnerError("discovery provisioning did not restore materialization inputs")

    def _reconcile_publication(self, position: int) -> None:
        record_path = self.repository.run_path / "records" / f"{position:08d}.json"
        record_before = record_path.read_bytes()
        record = read_json(record_path)
        ledger = read_json(self.repository.ledger_path)
        if not isinstance(record, dict) or not isinstance(ledger, dict):
            raise RunnerError("partial publication documents are invalid")
        if ledger.get("records_published") != position - 1:
            raise RunnerError("partial publication is not exactly one position")
        previous = None
        if position > 1:
            previous_record = read_json(
                self.repository.run_path / "records" / f"{position - 1:08d}.json"
            )
            previous = previous_record.get("record_sha256")
        if record.get("queue_position") != position or record.get(
            "previous_record_sha256"
        ) != previous:
            raise RunnerError("partial terminal record chain binding differs")
        updated = dict(ledger)
        updated["record_paths"] = [
            *ledger["record_paths"],
            str(RUN_RELATIVE_PATH / "records" / f"{position:08d}.json"),
        ]
        updated["records_published"] = position
        updated["state"] = record.get("stopping_rule_state_after_publication")
        source_root = str(self.repository.worktree / "src")
        inserted = source_root not in sys.path
        if inserted:
            sys.path.insert(0, source_root)
        try:
            from cmpilot.candidate_screening_v020 import (  # type: ignore
                ProtocolInvariantError,
                validate_published_successor_ledger,
            )

            records = [
                read_json(self.repository.run_path / "records" / f"{index:08d}.json")
                for index in range(1, position + 1)
            ]
            try:
                validate_published_successor_ledger(updated, records)
            except ProtocolInvariantError as error:
                raise RunnerError(
                    f"partial publication cannot produce valid replay: {error}"
                ) from error
        finally:
            if inserted:
                sys.path.remove(source_root)
        body = json.dumps(updated, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        sidecar = f"{sha256_bytes(body)}  ledger.json\n".encode("ascii")
        _atomic_bytes(self.repository.ledger_path, body)
        _atomic_bytes(self.repository.ledger_sidecar_path, sidecar)
        if record_path.read_bytes() != record_before:
            raise RunnerError("terminal publication recovery changed record bytes")
        self.repository._snapshot_at_actual_head()
        self._commit(
            f"Reconcile interrupted position {position} terminal publication",
            [record_path, self.repository.ledger_path, self.repository.ledger_sidecar_path],
            position,
        )


def _atomic_bytes(path: Path, body: bytes) -> None:
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class DurableStateMachine:
    def __init__(
        self,
        repository: ProductionRepositoryV2,
        executor: CodexRoleExecutorV2,
        logger: StructuredLogger,
        heartbeat: Heartbeat,
    ) -> None:
        self.repository = repository
        self.executor = executor
        self.logger = logger
        self.heartbeat = heartbeat
        self.classifier = DurableClassifier(repository)
        self.recovery = RecoveryEngine(repository, logger, heartbeat)
        self.last_successful_transition = "STARTUP_RECONCILIATION"
        self.positions_completed = 0

    def _emit_blocker(
        self,
        snapshot: legacy.Snapshot,
        *,
        category: str,
        code: str,
        role: str,
        reason: str,
        exact_missing_interface: str | None = None,
    ) -> RunnerOutcome:
        ledger_sha = sha256_file(self.repository.ledger_path)
        self.logger.emit_event(
            EventType.BLOCKER,
            blocker_category=category,
            blocker_code=code,
            position=snapshot.next_due_position,
            role=role,
            head=snapshot.head,
            ledger_sha256=ledger_sha,
            last_successful_transition=self.last_successful_transition,
            exact_missing_interface=exact_missing_interface,
            reason=reason,
        )
        return RunnerOutcome(
            EventType.BLOCKER,
            self.positions_completed,
            snapshot.next_due_position,
            reason,
        )

    def run(self, max_positions: int) -> RunnerOutcome:
        if isinstance(max_positions, bool) or max_positions <= 0:
            raise RunnerError("--max-positions must be a positive integer")
        completed = 0
        role_counts: dict[int, int] = {}
        while True:
            snapshot = self.repository.snapshot()
            self.heartbeat.update_snapshot(snapshot)
            if completed >= max_positions:
                self.logger.emit_event(
                    EventType.MAX_POSITION_STOP,
                    positions_completed=completed,
                    next_due_position=snapshot.next_due_position,
                    reason="configured terminal-position bound reached",
                )
                return RunnerOutcome(
                    EventType.MAX_POSITION_STOP,
                    completed,
                    snapshot.next_due_position,
                    "configured terminal-position bound reached",
                )
            try:
                classification = self.classifier.classify(snapshot)
            except legacy.CanonicalDecisionProcessingError as error:
                return self._emit_blocker(
                    snapshot,
                    category="ENGINEERING_BLOCKER",
                    code="CANONICAL_DECISION_PROCESSING_FAILED",
                    role="DURABLE_RECONCILIATION",
                    reason=str(error),
                )
            self.logger.emit_event(
                EventType.DURABLE_STATE_CLASSIFIED,
                durable_state=classification.state.value,
                position=snapshot.next_due_position,
                head=snapshot.head,
                ledger_sha256=sha256_file(self.repository.ledger_path),
                next_role=(
                    classification.next_role.value
                    if classification.next_role is not None
                    else None
                ),
                reason=classification.reason,
            )
            if classification.state is DurableState.GLOBAL_STOP:
                self.logger.emit_event(
                    EventType.GLOBAL_STOP,
                    position=snapshot.next_due_position,
                    global_action=snapshot.global_action,
                    reason=classification.reason,
                )
                return RunnerOutcome(
                    EventType.GLOBAL_STOP,
                    completed,
                    snapshot.next_due_position,
                    classification.reason,
                )
            if classification.recovery_id is not None:
                try:
                    self.recovery.run(classification, snapshot.next_due_position)
                except RunnerError as error:
                    return self._emit_blocker(
                        snapshot,
                        category="DETERMINISTIC_RECOVERY",
                        code="RECOVERY_FAILED",
                        role="DETERMINISTIC_RECOVERY",
                        reason=str(error),
                        exact_missing_interface=(
                            BLOCKER_STAGE
                            if classification.recovery_id
                            == "CURRENT_POSITION_MATERIALIZATION"
                            else None
                        ),
                    )
                self.last_successful_transition = classification.recovery_id
                continue
            role = classification.next_role or STATE_ROLE_HANDLERS[classification.state]
            if role is None:
                return self._emit_blocker(
                    snapshot,
                    category="UNKNOWN_DURABLE_STATE",
                    code="NO_PERMITTED_HANDLER",
                    role="NONE",
                    reason=f"no handler for {classification.state.value}",
                )
            position = snapshot.next_due_position
            transitions = role_counts.get(position, 0)
            if transitions >= MAX_ROLE_TRANSITIONS_PER_POSITION:
                return self._emit_blocker(
                    snapshot,
                    category="ROLE_TRANSITION_CEILING",
                    code="NONTERMINAL_LOOP",
                    role=role.value,
                    reason="role-transition ceiling reached without terminal publication",
                )
            before = self.repository.durable_token(position)
            attempts = 0
            network_retries = (
                getattr(self.heartbeat, "network_retry_count", 0)
                if getattr(self.heartbeat, "network_retry_role", None) == role.value
                and getattr(self.heartbeat, "network_retry_position", None) == position
                else 0
            )
            while True:
                try:
                    execution = self.executor.execute(role, position, snapshot.head)
                except (
                    legacy.ProviderEvidenceReferenceContractError,
                    ProviderEvidenceReferenceContractIncompatible,
                ) as error:
                    raw_snapshot = self.repository._snapshot_at_actual_head()
                    if (
                        raw_snapshot.head != before.head
                        or self.repository.durable_token(position) != before
                    ):
                        return self._emit_blocker(
                            raw_snapshot,
                            category="AI_REVIEW_ISOLATION",
                            code="EVIDENCE_CONTRACT_PREFLIGHT_DURABLE_STATE_CHANGED",
                            role=role.value,
                            reason=str(error),
                        )
                    return self._emit_blocker(
                        raw_snapshot,
                        category="ENGINEERING_BLOCKER",
                        code="PROVIDER_EVIDENCE_REFERENCE_CONTRACT_INCOMPATIBLE",
                        role=role.value,
                        reason=str(error),
                    )
                except ProviderOutputSchemaIncompatible as error:
                    raw_snapshot = self.repository._snapshot_at_actual_head()
                    if (
                        raw_snapshot.head != before.head
                        or self.repository.durable_token(position) != before
                    ):
                        return self._emit_blocker(
                            raw_snapshot,
                            category="AI_REVIEW_ISOLATION",
                            code="OUTPUT_SCHEMA_PREFLIGHT_DURABLE_STATE_CHANGED",
                            role=role.value,
                            reason=str(error),
                        )
                    return self._emit_blocker(
                        raw_snapshot,
                        category="ENGINEERING_BLOCKER",
                        code="PROVIDER_OUTPUT_SCHEMA_INCOMPATIBLE",
                        role=role.value,
                        reason=str(error),
                    )
                except ReviewSandboxNetworkUnavailable as error:
                    raw_snapshot = self.repository._snapshot_at_actual_head()
                    if (
                        raw_snapshot.head != before.head
                        or self.repository.durable_token(position) != before
                    ):
                        return self._emit_blocker(
                            raw_snapshot,
                            category="AI_REVIEW_ISOLATION",
                            code="NETWORK_PREFLIGHT_DURABLE_STATE_CHANGED",
                            role=role.value,
                            reason=str(error),
                        )
                    return self._emit_blocker(
                        raw_snapshot,
                        category="ENGINEERING_BLOCKER",
                        code="REVIEW_SANDBOX_NETWORK_UNAVAILABLE",
                        role=role.value,
                        reason=str(error),
                    )
                self.logger.emit_event(
                    EventType.ROLE_COMPLETED,
                    position=position,
                    role=role.value,
                    invocation_id=execution.invocation_id,
                    exit_code=execution.exit_code,
                    prompt_sha256=execution.prompt_sha256,
                    head_before=before.head,
                    head_after_process=self.repository.actual_head(),
                    codex_thread_id=execution.codex_thread_id,
                    model_identifier=execution.model_identifier,
                    stdout_sha256=sha256_bytes(execution.stdout.encode("utf-8")),
                    stderr_sha256=sha256_bytes(execution.stderr.encode("utf-8")),
                    stdout_bytes=len(execution.stdout.encode("utf-8")),
                    stderr_bytes=len(execution.stderr.encode("utf-8")),
                    infrastructure_failure=execution.infrastructure_failure,
                    partial_decision_present=execution.partial_decision_present,
                    reason="role process exited; durable reconciliation follows",
                )
                actual = self.repository.actual_head()
                changed = actual != before.head
                if role in {legacy.Role.AI_FIRST_REVIEW, legacy.Role.AI_SECOND_REVIEW}:
                    if (
                        execution.infrastructure_failure
                        == INVALID_PROVIDER_SCHEMA_FAILURE
                    ):
                        raw_snapshot = self.repository._snapshot_at_actual_head()
                        if raw_snapshot.head != before.head:
                            return self._emit_blocker(
                                raw_snapshot,
                                category="AI_REVIEW_ISOLATION",
                                code="REVIEWER_PRODUCTION_HEAD_CHANGED",
                                role=role.value,
                                reason=(
                                    "provider-schema-rejected reviewer observed an "
                                    "unexpected production HEAD change"
                                ),
                            )
                        if self.repository.durable_token(position) != before:
                            return self._emit_blocker(
                                raw_snapshot,
                                category="AI_REVIEW_VALIDATION",
                                code="AMBIGUOUS_DURABLE_REVIEW_STATE",
                                role=role.value,
                                reason=(
                                    "durable reviewer boundary changed after provider "
                                    "schema rejection"
                                ),
                            )
                        return self._emit_blocker(
                            raw_snapshot,
                            category="ENGINEERING_BLOCKER",
                            code="PROVIDER_OUTPUT_SCHEMA_REJECTED",
                            role=role.value,
                            reason=(
                                "invalid_json_schema at text.format.schema; interface "
                                "failure is non-network and non-retryable"
                            ),
                        )
                    if execution.infrastructure_failure == "CODEX_NETWORK_STALL":
                        raw_snapshot = self.repository._snapshot_at_actual_head()
                        decision_name = (
                            "ai-reviewer-a-decision.json"
                            if role is legacy.Role.AI_FIRST_REVIEW
                            else "ai-reviewer-b-decision.json"
                        )
                        if (self.repository.position_path(position) / decision_name).exists():
                            return self._emit_blocker(
                                raw_snapshot,
                                category="AI_REVIEW_VALIDATION",
                                code="DECISION_PRESENT_AFTER_NETWORK_STALL",
                                role=role.value,
                                reason=(
                                    "review decision exists after network stall; "
                                    "automatic retry is prohibited"
                                ),
                            )
                        if execution.partial_decision_present:
                            return self._emit_blocker(
                                raw_snapshot,
                                category="AI_REVIEW_VALIDATION",
                                code="AMBIGUOUS_PARTIAL_REVIEW_DECISION",
                                role=role.value,
                                reason=(
                                    "reviewer last-message output exists after network "
                                    "stall; automatic retry is prohibited"
                                ),
                            )
                        if raw_snapshot.head != before.head:
                            return self._emit_blocker(
                                raw_snapshot,
                                category="AI_REVIEW_ISOLATION",
                                code="REVIEWER_PRODUCTION_HEAD_CHANGED",
                                role=role.value,
                                reason=(
                                    "network-stalled reviewer boundary observed an "
                                    "unexpected production HEAD change"
                                ),
                            )
                        if self.repository.durable_token(position) != before:
                            return self._emit_blocker(
                                raw_snapshot,
                                category="AI_REVIEW_VALIDATION",
                                code="AMBIGUOUS_DURABLE_REVIEW_STATE",
                                role=role.value,
                                reason=(
                                    "candidate, packet, assignment, or position state "
                                    "changed during the stalled reviewer"
                                ),
                            )
                        raw_classification = self.classifier.classify(raw_snapshot)
                        self.logger.emit_event(
                            EventType.DURABLE_STATE_CLASSIFIED,
                            durable_state=raw_classification.state.value,
                            position=raw_snapshot.next_due_position,
                            head=raw_snapshot.head,
                            ledger_sha256=sha256_file(self.repository.ledger_path),
                            role=role.value,
                            reason="network-stalled reviewer reconciled from durable state",
                        )
                        if (
                            raw_classification.state is not classification.state
                            or raw_classification.next_role is not role
                        ):
                            return self._emit_blocker(
                                raw_snapshot,
                                category="AI_REVIEW_VALIDATION",
                                code="REVIEW_BOUNDARY_CHANGED_AFTER_NETWORK_STALL",
                                role=role.value,
                                reason="durable reviewer boundary changed; retry prohibited",
                            )
                        if network_retries >= MAX_NETWORK_STALL_RETRIES:
                            return self._emit_blocker(
                                raw_snapshot,
                                category="ENGINEERING_BLOCKER",
                                code="NETWORK_STALL_RETRY_EXHAUSTED",
                                role=role.value,
                                reason=(
                                    "initial reviewer plus two fresh network-stall "
                                    "retries exhausted"
                                ),
                            )
                        network_retries += 1
                        self.heartbeat.set_review_attempt(
                            self.heartbeat.review_attempt, network_retries
                        )
                        continue
                    if execution.exit_code == 0:
                        try:
                            self.repository.accept_reviewer(execution, before)
                        except legacy.CanonicalDecisionProcessingError as error:
                            return self._emit_blocker(
                                snapshot,
                                category="ENGINEERING_BLOCKER",
                                code="CANONICAL_DECISION_PROCESSING_FAILED",
                                role=role.value,
                                reason=str(error),
                            )
                        except legacy.ProviderEvidenceReferenceContractError as error:
                            return self._emit_blocker(
                                snapshot,
                                category="ENGINEERING_BLOCKER",
                                code="PROVIDER_EVIDENCE_REFERENCE_CONTRACT_INVALID",
                                role=role.value,
                                reason=str(error),
                            )
                        except legacy.RunnerError as error:
                            return self._emit_blocker(
                                snapshot,
                                category="AI_REVIEW_VALIDATION",
                                code=(
                                    "INVALID_AI_A"
                                    if role is legacy.Role.AI_FIRST_REVIEW
                                    else "INVALID_AI_B"
                                ),
                                role=role.value,
                                reason=str(error),
                            )
                    else:
                        raw_snapshot = self.repository._snapshot_at_actual_head()
                        raw_classification = self.classifier.classify(raw_snapshot)
                        self.logger.emit_event(
                            EventType.DURABLE_STATE_CLASSIFIED,
                            durable_state=raw_classification.state.value,
                            position=raw_snapshot.next_due_position,
                            head=raw_snapshot.head,
                            ledger_sha256=sha256_file(self.repository.ledger_path),
                            role=role.value,
                            reason="failed reviewer process reconciled from durable state",
                        )
                        if raw_snapshot.head != before.head:
                            return self._emit_blocker(
                                raw_snapshot,
                                category="AI_REVIEW_ISOLATION",
                                code="REVIEWER_PRODUCTION_HEAD_CHANGED",
                                role=role.value,
                                reason="reviewer boundary observed an unexpected production HEAD change",
                            )
                        if (
                            self.repository.durable_token(position) == before
                            and attempts < SAFE_RETRY_LIMIT
                        ):
                            attempts += 1
                            continue
                        return self._emit_blocker(
                            snapshot,
                            category="CHILD_PROCESS",
                            code="REVIEWER_EXIT_WITHOUT_VALID_DECISION",
                            role=role.value,
                            reason=f"review child exit code {execution.exit_code}",
                        )
                else:
                    if not changed:
                        raw_snapshot = self.repository._snapshot_at_actual_head()
                        raw_classification = self.classifier.classify(raw_snapshot)
                        if raw_classification.recovery_id is not None:
                            self.recovery.run(raw_classification, position)
                            actual = self.repository.actual_head()
                            changed = actual != before.head
                        elif self.repository.commit_valid_uncommitted_transition(
                            position, raw_classification
                        ):
                            actual = self.repository.actual_head()
                            changed = actual != before.head
                    if changed:
                        if self.repository.state["expected_head"] != actual:
                            self.repository.accept_controller_head(execution, before)
                    elif execution.exit_code != 0 and attempts < SAFE_RETRY_LIMIT:
                        attempts += 1
                        continue
                    elif not changed:
                        return self._emit_blocker(
                            snapshot,
                            category="CHILD_PROCESS",
                            code=(
                                "CHILD_DISAPPEARED"
                                if execution.exit_code < 0
                                else "CONTROLLER_NO_DURABLE_TRANSITION"
                            ),
                            role=role.value,
                            reason=f"controller exit code {execution.exit_code} with no durable commit",
                        )
                break
            role_counts[position] = transitions + 1
            after = self.repository.snapshot()
            self.heartbeat.update_snapshot(after)
            try:
                after_classification = self.classifier.classify(after)
            except legacy.CanonicalDecisionProcessingError as error:
                return self._emit_blocker(
                    after,
                    category="ENGINEERING_BLOCKER",
                    code="CANONICAL_DECISION_PROCESSING_FAILED",
                    role=role.value,
                    reason=str(error),
                )
            self.logger.emit_event(
                EventType.DURABLE_STATE_CLASSIFIED,
                durable_state=after_classification.state.value,
                position=after.next_due_position,
                head=after.head,
                ledger_sha256=sha256_file(self.repository.ledger_path),
                role=role.value,
                reason="post-role durable reconciliation",
            )
            if role is legacy.Role.AI_FIRST_REVIEW:
                self.logger.emit_event(
                    EventType.AI_REVIEW_A,
                    position=position,
                    role=role.value,
                    head=after.head,
                    durable_state=after_classification.state.value,
                    reason="authoritative AI-A decision validated and committed",
                )
            elif role is legacy.Role.AI_SECOND_REVIEW:
                self.logger.emit_event(
                    EventType.AI_REVIEW_B,
                    position=position,
                    role=role.value,
                    head=after.head,
                    durable_state=after_classification.state.value,
                    reason="authoritative blinded AI-B decision validated and committed",
                )
            elif role in {
                legacy.Role.CONTINUATION_CONTROLLER,
                legacy.Role.COMBINATION_CONTINUATION_CONTROLLER,
            }:
                self.logger.emit_event(
                    EventType.COMBINATION_CONTINUATION,
                    position=position,
                    role=role.value,
                    head=after.head,
                    durable_state=after_classification.state.value,
                    reason="continuation transition validated from durable repository state",
                )
            if after.records_published == snapshot.records_published + 1:
                if (
                    after.next_due_position != position + 1
                    or after.successor_positions_processed
                    != snapshot.successor_positions_processed + 1
                ):
                    return self._emit_blocker(
                        after,
                        category="PUBLICATION",
                        code="NON_UNIT_LEDGER_TRANSITION",
                        role=role.value,
                        reason="terminal publication did not advance exactly one position",
                    )
                terminal = self.repository.last_terminal_processing_state(position)
                if terminal not in legacy.TERMINAL_AUTOCONTINUE_STATES:
                    return self._emit_blocker(
                        after,
                        category="PUBLICATION",
                        code="UNRECOGNIZED_TERMINAL_STATE",
                        role=role.value,
                        reason=f"terminal processing state is {terminal}",
                    )
                next_root = self.repository.position_path(after.next_due_position)
                next_record = self.repository.run_path / "records" / (
                    f"{after.next_due_position:08d}.json"
                )
                if next_root.exists() or next_record.exists():
                    return self._emit_blocker(
                        after,
                        category="FUTURE_POSITION",
                        code="NEXT_POSITION_PREOPENED",
                        role=role.value,
                        reason="next due position already contains durable state",
                    )
                completed += 1
                self.positions_completed = completed
                self.last_successful_transition = f"TERMINAL_PUBLISHED_{position}"
                self.logger.emit_event(
                    EventType.DURABLE_STATE_CLASSIFIED,
                    durable_state=DurableState.TERMINAL_PUBLISHED.value,
                    position=position,
                    head=after.head,
                    ledger_sha256=sha256_file(self.repository.ledger_path),
                    reason="terminal record and unit ledger transition replayed successfully",
                )
                if after.global_action != "CONTINUE":
                    self.logger.emit_event(
                        EventType.GLOBAL_STOP,
                        position=after.next_due_position,
                        global_action=after.global_action,
                        reason="terminal publication activated the frozen global stop",
                    )
                    return RunnerOutcome(
                        EventType.GLOBAL_STOP,
                        completed,
                        after.next_due_position,
                        "terminal publication activated the frozen global stop",
                    )
                self.logger.emit_event(
                    EventType.AUTO_CONTINUE,
                    position=position,
                    terminal_processing_state=terminal,
                    records_published=after.records_published,
                    next_due_position=after.next_due_position,
                    head=after.head,
                    ledger_sha256=sha256_file(self.repository.ledger_path),
                    reason="record, unit ledger transition, and full replay validated",
                )
            elif after.records_published != snapshot.records_published:
                return self._emit_blocker(
                    after,
                    category="PUBLICATION",
                    code="NON_UNIT_RECORD_COUNT",
                    role=role.value,
                    reason="role changed published record count by more than one",
                )
            else:
                self.last_successful_transition = after_classification.state.value


def _heartbeat_value(root: Path) -> dict[str, Any] | None:
    heartbeat_path = root / "state" / "heartbeat.json"
    if not heartbeat_path.exists():
        return None
    if heartbeat_path.is_symlink() or not heartbeat_path.is_file():
        raise RunnerError("heartbeat path is not a regular file")
    value = read_json(heartbeat_path)
    if not isinstance(value, dict):
        raise RunnerError("heartbeat must be an object")
    return value


def _heartbeat_age(value: Mapping[str, Any]) -> tuple[int | None, str | None]:
    timestamp = value.get("heartbeat_timestamp")
    if not isinstance(timestamp, str):
        return None, "heartbeat timestamp is absent"
    try:
        parsed = parse_utc(timestamp)
    except (TypeError, ValueError) as error:
        return None, f"heartbeat timestamp is invalid: {error}"
    return max(0, int((datetime.now(UTC) - parsed).total_seconds())), None


def _historical_pid(
    value: Mapping[str, Any], history_key: str, active_key: str
) -> int | None:
    historical = value.get(history_key)
    if isinstance(historical, int) and not isinstance(historical, bool) and historical > 0:
        return historical
    active = value.get(active_key)
    if isinstance(active, int) and not isinstance(active, bool) and active > 0:
        return active
    return None


def status_command(root: Path) -> int:
    value = _heartbeat_value(root)
    if value is None:
        print("STATUS: STOPPED")
        print("RUNNER_PID: -")
        print("CHILD_PID: -")
        print("LAST_REASON: heartbeat has never been written")
        print(f"LOG_DIR: {root / 'logs'}")
        return 0
    age, timestamp_reason = _heartbeat_age(value)
    recorded_status = value.get("status")
    recorded_runner_pid = value.get("runner_pid")
    recorded_child_pid = value.get("child_pid")
    effective_status: str
    runner_pid: int | None = None
    child_pid: int | None = None
    status_reason: str | None = None
    child_status: str | None = None
    if recorded_status == "STOPPED":
        effective_status = "STOPPED"
    elif recorded_status != "RUNNING":
        effective_status = "STALE"
        status_reason = f"heartbeat status is invalid: {recorded_status!r}"
    elif not process_alive(recorded_runner_pid):
        effective_status = "STALE"
        status_reason = "heartbeat says RUNNING but runner process is absent"
    elif timestamp_reason is not None:
        effective_status = "STALE"
        runner_pid = recorded_runner_pid
        status_reason = timestamp_reason
    elif age is not None and age > HEARTBEAT_STALE_SECONDS:
        effective_status = "STALE"
        runner_pid = recorded_runner_pid
        status_reason = (
            f"heartbeat is {age}s old (limit={HEARTBEAT_STALE_SECONDS}s)"
        )
    else:
        effective_status = "RUNNING"
        runner_pid = recorded_runner_pid

    if effective_status in {"RUNNING", "STALE"} and runner_pid is not None:
        if recorded_child_pid is not None and process_alive(recorded_child_pid):
            child_pid = recorded_child_pid
        elif recorded_child_pid is not None:
            child_status = "DISAPPEARED"
            if status_reason is None:
                status_reason = (
                    "heartbeat records a child process that is absent; "
                    "durable reconciliation pending"
                )
    latest = root / "state" / "latest-run.json"
    log_dir = root / "logs"
    if latest.is_file():
        latest_value = read_json(latest)
        if isinstance(latest_value, dict):
            log_dir = Path(latest_value.get("log_dir", log_dir))
    event_age = None
    event_timestamp = value.get("last_event_timestamp")
    if isinstance(event_timestamp, str):
        event_age = max(
            0, int((datetime.now(UTC) - parse_utc(event_timestamp)).total_seconds())
        )
    rows = [
        ("STATUS", effective_status),
        ("RUNNER_PID", runner_pid),
        ("CHILD_PID", child_pid),
        ("LAST_RUNNER_PID", _historical_pid(value, "last_runner_pid", "runner_pid")),
        ("LAST_CHILD_PID", _historical_pid(value, "last_child_pid", "child_pid")),
        ("POSITION", value.get("position", value.get("current_position"))),
        ("ROLE", value.get("role", value.get("current_role"))),
        ("HEAD", value.get("production_head")),
        ("RECORDS_PUBLISHED", value.get("records_published")),
        ("NEXT_DUE_POSITION", value.get("next_due_position")),
        ("NETWORK_STATE", value.get("network_state", "NOT_RECORDED")),
        ("NETWORK_WAIT_SECONDS", value.get("network_wait_seconds", 0)),
        ("REVIEW_ATTEMPT", value.get("review_attempt", 0)),
        ("NETWORK_RETRY_COUNT", value.get("network_retry_count", 0)),
        ("NETWORK_FAILURE_SINCE", value.get("network_failure_since")),
        ("SECONDS_IN_ROLE", value.get("seconds_in_current_role")),
        ("SECONDS_SINCE_EVENT", event_age),
        ("SECONDS_SINCE_HEARTBEAT", age),
        ("LAST_EVENT", value.get("last_event")),
        ("LAST_CLASSIFICATION", value.get("last_classification")),
        ("LAST_REASON", value.get("last_reason")),
        ("LOG_DIR", log_dir),
    ]
    if effective_status == "STALE":
        rows.insert(3, ("RECORDED_RUNNER_PID", recorded_runner_pid))
    if child_status is not None:
        rows.insert(4, ("RECORDED_CHILD_PID", recorded_child_pid))
        rows.insert(5, ("CHILD_STATUS", child_status))
    if status_reason is not None:
        rows.insert(1, ("REASON", status_reason))
    for key, item in rows:
        print(f"{key}: {'-' if item is None else item}")
    return 0


def events_command(root: Path, limit: int) -> int:
    latest = root / "state" / "latest-run.json"
    if not latest.is_file():
        print("No Track A events have been recorded.")
        return 0
    value = read_json(latest)
    events_path = Path(value["events_path"])
    if not events_path.is_file():
        print("No Track A events have been recorded.")
        return 0
    lines = events_path.read_text(encoding="utf-8").splitlines()[-limit:]
    for line in lines:
        event = json.loads(line)
        print(
            "{timestamp} {event} position={position} role={role} state={state} "
            "network={network} review_attempt={attempt} network_retry_count={retries} "
            "network_failure_since={failure_since} reason={reason}".format(
                timestamp=event.get("timestamp_utc", "-"),
                event=event.get("event_type", "-"),
                position=event.get("position", "-"),
                role=event.get("role", "-"),
                state=event.get("durable_state", "-"),
                network=event.get("network_state", "-"),
                attempt=event.get("review_attempt", "-"),
                retries=event.get("network_retry_count", "-"),
                failure_since=event.get("network_failure_since", "-"),
                reason=event.get("reason", "-"),
            )
        )
    return 0


def _lock_owner_pids(path: Path) -> tuple[tuple[int, ...], bool]:
    try:
        stat = path.stat()
        lines = Path("/proc/locks").read_text(encoding="ascii").splitlines()
    except OSError:
        return (), False
    expected = (os.major(stat.st_dev), os.minor(stat.st_dev), stat.st_ino)

    def owner_holds_target(owner: int) -> bool:
        descriptor_root = Path(f"/proc/{owner}/fd")
        try:
            descriptors = tuple(descriptor_root.iterdir())
        except OSError:
            return False
        for descriptor in descriptors:
            try:
                descriptor_stat = descriptor.stat()
            except OSError:
                continue
            if (descriptor_stat.st_dev, descriptor_stat.st_ino) == (
                stat.st_dev,
                stat.st_ino,
            ):
                return True
        return False

    owners: set[int] = set()
    for line in lines:
        fields = line.replace("->", "").split()
        for index, field in enumerate(fields):
            parts = field.split(":")
            if len(parts) != 3 or index == 0:
                continue
            try:
                identity = (int(parts[0], 16), int(parts[1], 16), int(parts[2]))
                owner = int(fields[index - 1])
            except ValueError:
                continue
            exact_identity = identity == expected
            # Some mounted filesystems expose a different device minor through
            # /proc/locks than through stat(2).  In that case, use the inode only
            # to find a candidate and prove the exact target through its open fd.
            verified_mounted_identity = (
                identity[2] == expected[2] and owner > 0 and owner_holds_target(owner)
            )
            if owner > 0 and (exact_identity or verified_mounted_identity):
                owners.add(owner)
    return tuple(sorted(owners)), True


def _lock_observation(root: Path) -> LockObservation:
    path = root / "track-a-runner.lock"
    if not path.exists():
        return LockObservation("ABSENT")
    if path.is_symlink() or not path.is_file():
        raise RunnerError("runner lock path is not a regular file")
    acquired = False
    with path.open("rb") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            owners, available = _lock_owner_pids(path)
            return LockObservation("HELD", owners, available)
        else:
            acquired = True
        finally:
            if acquired:
                try:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
    return LockObservation("FREE")


def _lock_status(root: Path) -> str:
    return _lock_observation(root).status


def _verify_lock_invariant(root: Path) -> LockObservation:
    observation = _lock_observation(root)
    heartbeat = _heartbeat_value(root)
    if observation.status != "HELD":
        if (
            heartbeat is not None
            and heartbeat.get("status") == "RUNNING"
            and process_alive(heartbeat.get("runner_pid"))
        ):
            raise RunnerError(
                f"heartbeat runner_pid={heartbeat.get('runner_pid')} is live but "
                f"flock status is {observation.status}"
            )
        return observation
    if heartbeat is None or heartbeat.get("status") != "RUNNING":
        raise RunnerError("flock is held without a RUNNING heartbeat")
    runner_pid = heartbeat.get("runner_pid")
    if not process_alive(runner_pid):
        raise RunnerError(f"flock is held but runner_pid={runner_pid!r} is not live")
    if not observation.owner_lookup_available:
        raise RunnerError("flock owner PID is unavailable; ownership cannot be proven")
    if runner_pid not in observation.owner_pids:
        raise RunnerError(
            f"flock owner_pids={list(observation.owner_pids)} differ from "
            f"heartbeat runner_pid={runner_pid}"
        )
    return observation


def _verify_heartbeat_invariant(root: Path) -> str:
    value = _heartbeat_value(root)
    lock = _lock_observation(root)
    if value is None:
        if lock.status == "HELD":
            raise RunnerError("flock is held but heartbeat is absent")
        return "heartbeat=ABSENT; no active runner required"
    schema = value.get("schema")
    status = value.get("status")
    runner_pid = value.get("runner_pid")
    child_pid = value.get("child_pid")
    if schema != HEARTBEAT_SCHEMA:
        stale_fields = []
        if runner_pid is not None:
            stale_fields.append(f"runner_pid={runner_pid}")
        if child_pid is not None:
            stale_fields.append(f"child_pid={child_pid}")
        suffix = f"; stale_active_fields={','.join(stale_fields)}" if stale_fields else ""
        raise RunnerError(
            f"heartbeat schema={schema!r} requires explicit normalization to "
            f"{HEARTBEAT_SCHEMA}{suffix}"
        )
    required = {"runner_pid", "child_pid", "last_runner_pid", "last_child_pid"}
    missing = sorted(required - set(value))
    if missing:
        raise RunnerError(f"heartbeat lifecycle fields are absent: {','.join(missing)}")
    if status == "STOPPED":
        if runner_pid is not None or child_pid is not None:
            raise RunnerError(
                "STOPPED heartbeat has non-null active PID fields: "
                f"runner_pid={runner_pid!r}, child_pid={child_pid!r}"
            )
        if lock.status == "HELD":
            raise RunnerError("STOPPED heartbeat is incoherent with a held flock")
        return (
            "status=STOPPED; runner_pid=null; child_pid=null; "
            f"last_runner_pid={value.get('last_runner_pid')!r}; "
            f"last_child_pid={value.get('last_child_pid')!r}"
        )
    if status != "RUNNING":
        raise RunnerError(f"heartbeat status is invalid: {status!r}")
    if not process_alive(runner_pid):
        raise RunnerError(f"RUNNING heartbeat runner_pid={runner_pid!r} is not live")
    age, timestamp_reason = _heartbeat_age(value)
    if timestamp_reason is not None:
        raise RunnerError(timestamp_reason)
    if age is None or age > HEARTBEAT_STALE_SECONDS:
        raise RunnerError(
            f"RUNNING heartbeat age={age!r}s exceeds {HEARTBEAT_STALE_SECONDS}s"
        )
    if lock.status != "HELD":
        raise RunnerError(f"RUNNING heartbeat has flock status={lock.status}")
    if not lock.owner_lookup_available or runner_pid not in lock.owner_pids:
        raise RunnerError(
            f"RUNNING heartbeat runner_pid={runner_pid} does not own flock; "
            f"owner_pids={list(lock.owner_pids)}"
        )
    if child_pid is not None and not process_alive(child_pid):
        raise RunnerError(
            f"active child_pid={child_pid} is absent and durable reconciliation "
            "has not cleared the active field"
        )
    return (
        f"status=RUNNING; runner_pid={runner_pid}; child_pid={child_pid!r}; "
        f"flock_owner_pids={list(lock.owner_pids)}"
    )


def normalize_heartbeat_state(root: Path) -> dict[str, Any]:
    value = _heartbeat_value(root)
    if value is None:
        return {"changed": False, "result": "NO_HEARTBEAT"}
    runner_pid = value.get("runner_pid")
    child_pid = value.get("child_pid")
    if value.get("status") == "RUNNING" and process_alive(runner_pid):
        raise RunnerError(
            f"refusing to normalize live RUNNING heartbeat runner_pid={runner_pid}"
        )
    already_normal = (
        value.get("schema") == HEARTBEAT_SCHEMA
        and value.get("status") == "STOPPED"
        and runner_pid is None
        and child_pid is None
        and "last_runner_pid" in value
        and "last_child_pid" in value
    )
    if already_normal:
        return {"changed": False, "result": "ALREADY_NORMALIZED"}
    updated = dict(value)
    if isinstance(runner_pid, int) and not isinstance(runner_pid, bool) and runner_pid > 0:
        updated["last_runner_pid"] = runner_pid
    else:
        updated.setdefault("last_runner_pid", None)
    if isinstance(child_pid, int) and not isinstance(child_pid, bool) and child_pid > 0:
        updated["last_child_pid"] = child_pid
        updated["last_child_started_at_utc"] = value.get("child_started_at_utc")
    else:
        updated.setdefault("last_child_pid", None)
        updated.setdefault("last_child_started_at_utc", None)
    role = value.get("role", value.get("current_role"))
    if role is not None:
        updated["last_role"] = role
    updated.update(
        {
            "schema": HEARTBEAT_SCHEMA,
            "status": "STOPPED",
            "runner_pid": None,
            "child_pid": None,
            "child_started_at_utc": None,
            "role": None,
            "current_role": None,
            "normalization_id": HEARTBEAT_NORMALIZATION_ID,
            "normalized_at_utc": utc_now(),
        }
    )
    atomic_json(root / "state" / "heartbeat.json", updated)
    return {
        "changed": True,
        "result": "NORMALIZED",
        "last_runner_pid": updated.get("last_runner_pid"),
        "last_child_pid": updated.get("last_child_pid"),
    }


def normalize_operational_state_command(
    worktree: Path, root: Path, state_file: Path
) -> int:
    worktree = worktree.resolve()
    root = root.resolve()
    if root == worktree or worktree in root.parents:
        raise RunnerError("runner root must remain outside production worktree")
    lock = _lock_observation(root)
    if lock.status != "HELD":
        raise RunnerError("operational-state normalization requires the runner flock")
    if lock.owner_lookup_available and os.getpid() not in lock.owner_pids:
        raise RunnerError(
            f"normalization process does not own runner flock: {list(lock.owner_pids)}"
        )

    class NormalizationLogger:
        run_dir = root / "logs" / "normalization-read-only"

        def emit_event(self, *args: Any, **kwargs: Any) -> None:
            return None

    repository = ProductionRepositoryV2(
        worktree, root, state_file, NormalizationLogger()  # type: ignore[arg-type]
    )
    if repository.branch() != EXPECTED_BRANCH:
        raise RunnerError(f"production branch differs: {repository.branch()}")
    tracked = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=no"],
        cwd=worktree,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        env=legacy.sanitized_environment(),
    )
    if tracked.returncode != 0 or tracked.stdout:
        raise RunnerError("tracked production worktree/index must be clean")
    manifest = repository._verify_amendment_chain(require_state_binding=False)
    snapshot = repository._snapshot_at_actual_head()
    classification = DurableClassifier(repository).classify(snapshot)
    if (
        snapshot.records_published != 21
        or snapshot.next_due_position != 22
        or classification.state is not DurableState.AI_SECOND_ASSIGNMENT_REQUIRED
        or classification.recovery_id is not None
        or classification.next_role is not legacy.Role.CONTINUATION_CONTROLLER
    ):
        raise RunnerError("production boundary differs; normalization refused")
    blocker = repository.position_path(22) / "autonomous-blocker.json"
    if not blocker.is_file() or sha256_file(blocker) != BLOCKER_SHA256:
        raise RunnerError("Position 22 blocker identity differs")
    decision_a = repository.position_path(22) / "ai-reviewer-a-decision.json"
    if (
        not decision_a.is_file()
        or sha256_file(decision_a)
        != "06465e9f58a4d03ecaa09390b62571903ccb6e13edde73ae9cb9cc744c6c79ea"
    ):
        raise RunnerError("Position 22 authoritative AI-A decision identity differs")
    forbidden = (
        repository.position_path(22) / "ai-reviewer-b-decision.json",
        repository.position_path(22) / "terminal-record.json",
        repository.run_path / "records" / "00000022.json",
        repository.position_path(23),
        repository.run_path / "records" / "00000023.json",
    )
    if any(path.exists() for path in forbidden):
        raise RunnerError("Position 22/23 production boundary changed; normalization refused")
    actual = snapshot.head
    expected = repository.state["expected_head"]
    authorized_paths = {
        row.get("path")
        for row in manifest.get("repository_artifacts", [])
        if isinstance(row, dict) and isinstance(row.get("path"), str)
    }
    authorized_paths.update(
        {
            f"{CANONICAL_RECONCILIATION_CORRECTION_RELATIVE_PATH}/freeze-manifest.json",
            f"{CANONICAL_RECONCILIATION_CORRECTION_RELATIVE_PATH}/freeze-manifest.json.sha256",
        }
    )
    if actual != expected:
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", expected, actual],
            cwd=worktree,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            env=legacy.sanitized_environment(),
        )
        changed = repository._git(
            "diff", "--name-only", f"{expected}..{actual}"
        ).splitlines()
        if (
            ancestor.returncode != 0
            or not changed
            or any(path not in authorized_paths for path in changed)
        ):
            raise RunnerError(
                "HEAD migration contains paths outside the canonical reconciliation correction"
            )
    manifest_relative = (
        f"{CANONICAL_RECONCILIATION_CORRECTION_RELATIVE_PATH}/freeze-manifest.json"
    )
    committed = subprocess.run(
        ["git", "cat-file", "-e", f"{actual}:{manifest_relative}"],
        cwd=worktree,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        env=legacy.sanitized_environment(),
    )
    if committed.returncode != 0:
        raise RunnerError("canonical reconciliation correction freeze is not committed at HEAD")
    manifest_path = worktree / manifest_relative
    updated_state = dict(repository.state)
    updated_state["expected_head"] = actual
    updated_state["amendment_manifest_sha256"] = sha256_file(manifest_path)
    state_changed = updated_state != repository.state
    if state_changed:
        atomic_json(state_file, updated_state)
    heartbeat_result = normalize_heartbeat_state(root)
    print(f"OPERATIONAL_STATE_NORMALIZATION: PASS")
    print(f"CORRECTION_ID: {manifest.get('correction_id')}")
    print(f"RUNNER_STATE_CHANGED: {str(state_changed).lower()}")
    print(f"HEARTBEAT_RESULT: {heartbeat_result['result']}")
    print(f"PRODUCTION_HEAD: {actual}")
    print(f"POSITION: {snapshot.next_due_position}")
    print(f"RECORDS_PUBLISHED: {snapshot.records_published}")
    return 0


def doctor_command(
    worktree: Path,
    root: Path,
    state_file: Path,
    *,
    repository_factory: type[ProductionRepositoryV2] = ProductionRepositoryV2,
    reachable_recovery_validator: Any = validate_reachable_recovery_inputs,
    codex_bin: Path | None = None,
    network_probe: Any = None,
) -> int:
    checks: list[tuple[str, bool, str]] = []

    def check(name: str, operation: Any, detail: Any = str) -> Any:
        try:
            result = operation()
            if result is False:
                raise RunnerError("predicate returned false")
            rendered = detail(result) if callable(detail) else str(detail)
        except Exception as error:
            checks.append(
                (name, False, f"exception={type(error).__name__}: {error}")
            )
            return None
        checks.append((name, True, rendered if rendered else "ok"))
        return result

    def dependency(value: Any, name: str) -> Any:
        if value is None:
            raise RunnerError(f"dependency={name} failed")
        return value

    matrix_registry = check(
        "TRANSITION_AND_RECOVERY_DEFINITIONS",
        validate_transition_definitions,
        lambda result: (
            f"states={len(result[0]['states'])}; "
            f"recoveries={len(result[1]['recoveries'])}"
        ),
    )
    check(
        "TRANSITION_TEST_COVERAGE",
        validate_coverage_manifest,
        lambda result: (
            f"schema={result['schema']}; "
            f"scenarios={len(result['required_scenarios'])}; "
            f"states={len(result['state_coverage'])}"
        ),
    )
    check(
        "RUNNER_LOCK",
        lambda: _verify_lock_invariant(root),
        lambda result: (
            f"status={result.status}; owner_pids={list(result.owner_pids)}"
            if result.status == "HELD"
            else f"status={result.status}; no active owner"
        ),
    )
    codex_path = check(
        "CODEX_CLI_PRESENT",
        lambda: resolve_canonical_codex_executable(codex_bin),
        lambda result: (
            f"configured_path={FROZEN_CODEX_EXECUTABLE}; canonical_path={result}"
        ),
    )
    check(
        "CODEX_CLI_VERSION_AND_EXEC_OPTIONS",
        lambda: verify_codex_cli(
            codex_path if isinstance(codex_path, Path) else None, worktree
        ),
        lambda result: (
            f"version={result['version']}; "
            f"interface={result.get('interface', 'verified')}"
        ),
    )
    provider_compatibility = check(
        "AI_REVIEW_OUTPUT_SCHEMA_COMPATIBILITY",
        lambda: validate_provider_output_schema_for_role(
            worktree, legacy.Role.AI_FIRST_REVIEW
        ),
        lambda result: (
            f"schema_sha256={result['schema_sha256']}; "
            f"profile_sha256={result['profile_sha256']}"
        ),
    )
    check(
        "AI_FIRST_REVIEW_OUTPUT_SCHEMA",
        lambda: validate_provider_output_schema_for_role(
            worktree, legacy.Role.AI_FIRST_REVIEW
        ),
        lambda result: (
            f"role={result['role']}; path={result['schema_path']}; "
            f"sha256={result['schema_sha256']}"
        ),
    )
    check(
        "AI_SECOND_REVIEW_OUTPUT_SCHEMA",
        lambda: validate_provider_output_schema_for_role(
            worktree, legacy.Role.AI_SECOND_REVIEW
        ),
        lambda result: (
            f"role={result['role']}; path={result['schema_path']}; "
            f"sha256={result['schema_sha256']}"
        ),
    )
    check(
        "PROVIDER_TO_CANONICAL_PROJECTION",
        lambda: validate_synthetic_provider_projection(worktree),
        lambda result: (
            f"fixture_sha256={result['fixture_sha256']}; "
            f"projection_sha256={result['projection_sha256']}; "
            f"canonical_decision_sha256={result['canonical_decision_sha256']}"
        ),
    )

    class DoctorLogger:
        run_dir = root / "logs" / "doctor-read-only"

        def emit_event(self, *args: Any, **kwargs: Any) -> None:
            return None

    repository = check(
        "RUNNER_STATE",
        lambda: repository_factory(worktree, root, state_file, DoctorLogger()),  # type: ignore[arg-type]
        lambda result: (
            f"schema={result.state.get('schema', 'fixture')}; "
            f"expected_head={result.state.get('expected_head')}"
        ),
    )
    check(
        "AI_FIRST_REVIEW_EVIDENCE_REFERENCE_CONTRACT",
        lambda: validate_doctor_evidence_contract(
            dependency(repository, "RUNNER_STATE"),
            worktree,
            legacy.Role.AI_FIRST_REVIEW,
        ),
        lambda result: (
            f"role={result['role']}; refs={result['allowed_evidence_refs']}; "
            f"schema_sha256={result['provider_schema_sha256']}"
        ),
    )
    check(
        "AI_SECOND_REVIEW_EVIDENCE_REFERENCE_CONTRACT",
        lambda: validate_doctor_evidence_contract(
            dependency(repository, "RUNNER_STATE"),
            worktree,
            legacy.Role.AI_SECOND_REVIEW,
        ),
        lambda result: (
            f"role={result['role']}; refs={result['allowed_evidence_refs']}; "
            "ai_a_material_loaded="
            f"{str(result.get('ai_a_material_loaded', False)).lower()}"
        ),
    )

    def verify_branch() -> str:
        current = dependency(repository, "RUNNER_STATE").branch()
        if current != EXPECTED_BRANCH:
            raise RunnerError(
                f"expected={EXPECTED_BRANCH}; observed={current}"
            )
        return current

    check("PRODUCTION_BRANCH", verify_branch, lambda result: f"branch={result}")
    amendment = check(
        "FROZEN_AMENDMENT_HASHES",
        lambda: dependency(repository, "RUNNER_STATE")._verify_amendment_chain(),
        lambda result: (
            f"correction_id={result.get('correction_id', result.get('amendment_id'))}; "
            f"repository_artifacts={len(result.get('repository_artifacts', []))}"
        ),
    )
    check(
        "EXTERNAL_RUNNER_HASHES",
        lambda: dependency(amendment, "FROZEN_AMENDMENT_HASHES").get(
            "external_runner_artifacts"
        ),
        lambda result: (
            f"verified_count={len(result)}; "
            f"files={','.join(Path(row['path']).name for row in result)}"
        ),
    )
    snapshot = check(
        "LEDGER_CHECKSUM_AND_REPLAY",
        lambda: dependency(repository, "RUNNER_STATE")._snapshot_at_actual_head(),
        lambda result: (
            f"records={result.records_published}; "
            f"successors={result.successor_positions_processed}; "
            f"next_due={result.next_due_position}; action={result.global_action}"
        ),
    )

    def verify_head() -> str:
        current_repository = dependency(repository, "RUNNER_STATE")
        current_snapshot = dependency(snapshot, "LEDGER_CHECKSUM_AND_REPLAY")
        expected = current_repository.state.get("expected_head")
        if current_snapshot.head == expected:
            return f"exact={current_snapshot.head}"
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", expected, current_snapshot.head],
            cwd=current_repository.worktree,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            env=legacy.sanitized_environment(),
        )
        if ancestor.returncode != 0:
            raise RunnerError("actual HEAD is not the expected HEAD or its descendant")
        return f"recoverable_valid_descendant={current_snapshot.head}"

    check("PRODUCTION_HEAD", verify_head)
    classification = check(
        "CURRENT_DURABLE_CLASSIFICATION",
        lambda: DurableClassifier(
            dependency(repository, "RUNNER_STATE")
        ).classify(dependency(snapshot, "LEDGER_CHECKSUM_AND_REPLAY")),
        lambda result: (
            f"state={result.state.value}; recovery_id={result.recovery_id}; "
            f"next_role={result.next_role.value if result.next_role else None}"
        ),
    )
    check(
        "TRANSITION_HANDLER_COVERAGE",
        lambda: validate_runtime_interface_coverage(worktree),
        lambda result: (
            f"states={result['state_count']}; recoveries={result['recovery_count']}; "
            f"scenarios={result['scenario_count']}"
        ),
    )
    check(
        "MATERIALIZATION_INTERFACE",
        lambda: str(worktree / MATERIALIZER_RELATIVE_PATH)
        if (worktree / MATERIALIZER_RELATIVE_PATH).is_file()
        else (_ for _ in ()).throw(RunnerError("materializer missing")),
        lambda result: f"path={result}",
    )

    def verify_reachable() -> str:
        current = dependency(classification, "CURRENT_DURABLE_CLASSIFICATION")
        if (
            current.next_role is None
            and current.recovery_id not in RECOVERY_HANDLERS
            and current.state
            not in {DurableState.GLOBAL_STOP, DurableState.TERMINAL_PUBLISHED}
        ):
            raise RunnerError("reachable transition lacks interface")
        return (
            f"state={current.state.value}; recovery_id={current.recovery_id}; "
            f"next_role={current.next_role.value if current.next_role else None}"
        )

    check(
        "CURRENT_REACHABLE_INTERFACE",
        verify_reachable,
    )
    check(
        "CURRENT_POSITION_MATERIALIZATION_INPUTS",
        lambda: reachable_recovery_validator(
            dependency(repository, "RUNNER_STATE"),
            dependency(classification, "CURRENT_DURABLE_CLASSIFICATION"),
            dependency(snapshot, "LEDGER_CHECKSUM_AND_REPLAY").next_due_position,
        ),
        lambda result: (
            f"recovery_id={dependency(classification, 'CURRENT_DURABLE_CLASSIFICATION').recovery_id}; "
            f"position={dependency(snapshot, 'LEDGER_CHECKSUM_AND_REPLAY').next_due_position}; "
            f"tree_sha256={result.get('tree_sha256', 'NOT_APPLICABLE')}; "
            f"writes_performed={result.get('writes_performed', False)}"
        ),
    )

    def verify_review_sandbox_network() -> str:
        probe_operation = network_probe
        if probe_operation is None:
            probe_operation = lambda role: review_network.probe_reviewer_sandbox_network(
                runner_root=root,
                role=role.value,
                environment=legacy.sanitized_environment(),
            )
        results: list[review_network.SandboxNetworkProbe] = []
        for role in (
            legacy.Role.AI_FIRST_REVIEW,
            legacy.Role.AI_SECOND_REVIEW,
        ):
            result = probe_operation(role)
            if not result.passed:
                raise RunnerError(_network_probe_detail(result))
            results.append(result)
        if results[0].resolver_target != results[1].resolver_target:
            raise RunnerError("AI-A and AI-B resolver templates differ")
        return "; ".join(
            f"{result.role}=PASS(resolver={result.resolver_target},"
            f"dns={result.dns_status},https={result.https_status})"
            for result in results
        )

    check(
        "REVIEW_SANDBOX_NETWORK_PREFLIGHT",
        verify_review_sandbox_network,
    )

    def verify_operational_interfaces() -> str:
        source = Path(__file__).read_text(encoding="utf-8")
        required_tokens = (
            "heartbeat.json",
            "status_command",
            "events_command",
            "normalize_heartbeat_state",
            "heartbeat.stopped",
        )
        missing = [token for token in required_tokens if token not in source]
        if missing:
            raise RunnerError(
                f"operational status machinery missing: {','.join(missing)}"
            )
        return (
            f"schema={HEARTBEAT_SCHEMA}; status=read-only; events=read-only; "
            f"normalization={HEARTBEAT_NORMALIZATION_ID}"
        )

    check(
        "HEARTBEAT_STATUS_EVENTS",
        verify_operational_interfaces,
    )
    check("HEARTBEAT_LIFECYCLE", lambda: _verify_heartbeat_invariant(root))
    # The doctor invokes only Codex version/help commands.  It does not start a
    # Codex role, authorize a position, read a candidate manifest, or write state.
    del codex_path, matrix_registry, provider_compatibility
    for name, passed, detail in checks:
        print(f"{'PASS' if passed else 'FAIL'}: {name}: {detail}")
    failed_checks = [(name, detail) for name, passed, detail in checks if not passed]
    failed = bool(failed_checks)
    print(f"DOCTOR: {'FAIL' if failed else 'PASS'}")
    print(f"FAILED_CHECK_COUNT: {len(failed_checks)}")
    if failed_checks:
        print("FAILED_CHECKS:")
        for name, detail in failed_checks:
            print(f"- {name}: {detail}")
    else:
        print("FAILED_CHECKS: []")
    return 1 if failed else 0


def render_dry_run(
    repository: ProductionRepositoryV2,
    snapshot: legacy.Snapshot,
    classification: Classification,
    max_positions: int,
) -> str:
    before = repository.durable_token(snapshot.next_due_position)
    plan = {
        "schema": "track-a-dry-run-v0.2",
        "branch": EXPECTED_BRANCH,
        "head": snapshot.head,
        "records_published": snapshot.records_published,
        "next_due_position": snapshot.next_due_position,
        "durable_state": classification.state.value,
        "recovery_id": classification.recovery_id,
        "next_role": classification.next_role.value if classification.next_role else None,
        "max_terminal_positions": max_positions,
        "fresh_codex_process_per_role": True,
        "codex_resume": False,
        "codex_role_invocations": 0,
        "production_writes": 0,
        "position_23_opened": False,
    }
    after = repository.durable_token(snapshot.next_due_position)
    if before != after:
        raise RunnerError("dry run changed durable production state")
    return json.dumps(plan, indent=2, sort_keys=True) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Track A durable-state production reconciler")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--status", action="store_true")
    mode.add_argument("--events", action="store_true")
    mode.add_argument("--doctor", action="store_true")
    mode.add_argument("--normalize-operational-state", action="store_true")
    parser.add_argument("--max-positions", type=int, default=legacy.DEFAULT_MAX_POSITIONS)
    parser.add_argument("--event-limit", type=int, default=30)
    parser.add_argument("--worktree", type=Path, default=DEFAULT_WORKTREE)
    parser.add_argument(
        "--runner-root",
        type=Path,
        default=Path(os.environ.get("TRACK_A_RUNNER_ROOT", DEFAULT_RUNNER_ROOT)),
    )
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--codex-bin", type=Path)
    parser.add_argument("--model", default=legacy.DEFAULT_CODEX_MODEL)
    parser.add_argument("--profile")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    root = arguments.runner_root.resolve()
    state_file = arguments.state_file or root / "state" / "runner-state.json"
    if arguments.status:
        return status_command(root)
    if arguments.events:
        return events_command(root, arguments.event_limit)
    if arguments.doctor:
        return doctor_command(
            arguments.worktree.resolve(), root, state_file, codex_bin=arguments.codex_bin
        )
    if arguments.normalize_operational_state:
        try:
            return normalize_operational_state_command(
                arguments.worktree.resolve(), root, state_file
            )
        except RunnerError as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 1
    if arguments.max_positions <= 0:
        print("ERROR: --max-positions must be positive", file=sys.stderr)
        return 2
    runner_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12]
    heartbeat = Heartbeat(root, runner_id)
    logger: StructuredLogger | None = None
    snapshot: legacy.Snapshot | None = None
    final_reason = "runner exited before initialization"
    preflight_complete = False
    previous_handlers: dict[signal.Signals, Any] = {}

    def request_stop(signum: int, _frame: Any) -> None:
        raise RunnerError(f"termination signal {signal.Signals(signum).name} received")

    for handled_signal in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        previous_handlers[handled_signal] = signal.signal(handled_signal, request_stop)
    try:
        logger = StructuredLogger(root, runner_id, heartbeat)
        heartbeat.start()
        repository = ProductionRepositoryV2(
            arguments.worktree, root, state_file, logger
        )
        codex_bin = resolve_canonical_codex_executable(arguments.codex_bin)
        if (
            not arguments.dry_run
            and (
                arguments.model != legacy.DEFAULT_CODEX_MODEL
                or arguments.profile is not None
            )
        ):
            raise RunnerError("model/profile selector differs from frozen durable runner")
        snapshot = repository.preflight(
            dry_run=arguments.dry_run, codex_bin=codex_bin
        )
        heartbeat.update_snapshot(snapshot)
        heartbeat.write(status="RUNNING", force=True)
        classifier = DurableClassifier(repository)
        classification = classifier.classify(snapshot)
        if arguments.dry_run:
            report = render_dry_run(
                repository, snapshot, classification, arguments.max_positions
            )
            logger.emit_event(
                EventType.DRY_RUN,
                durable_state=classification.state.value,
                position=snapshot.next_due_position,
                recovery_id=classification.recovery_id,
                codex_role_invocations=0,
                reason="read-only durable plan validated",
            )
            sys.stdout.write(report)
            final_reason = "dry run complete"
            preflight_complete = True
            return 0
        if classification.next_role in {
            legacy.Role.AI_FIRST_REVIEW,
            legacy.Role.AI_SECOND_REVIEW,
        }:
            review_role = classification.next_role
            if (
                heartbeat.network_retry_role == review_role.value
                and heartbeat.network_retry_position == snapshot.next_due_position
                and heartbeat.network_retry_count >= MAX_NETWORK_STALL_RETRIES
            ):
                raise ReviewSandboxNetworkUnavailable(
                    "NETWORK_STALL_RETRY_EXHAUSTED: persisted retry bound "
                    "prohibits another reviewer launch"
                )
            heartbeat.set_role(review_role.value, None)
            wait_for_reviewer_network(
                role=review_role,
                position=snapshot.next_due_position,
                probe=lambda: review_network.probe_reviewer_sandbox_network(
                    runner_root=root,
                    role=review_role.value,
                    environment=legacy.sanitized_environment(),
                ),
                heartbeat=heartbeat,
                logger=logger,
            )
            heartbeat.set_role(None, None)
        preflight_complete = True
        executor = CodexRoleExecutorV2(
            repository,
            logger,
            codex_bin,
            arguments.model,
            arguments.profile,
            heartbeat=heartbeat,
        )
        machine = DurableStateMachine(repository, executor, logger, heartbeat)
        outcome = machine.run(arguments.max_positions)
        final_reason = outcome.reason
        print(
            json.dumps(
                {
                    "event": outcome.event.value,
                    "positions_completed": outcome.positions_completed,
                    "next_due_position": outcome.next_due_position,
                    "reason": outcome.reason,
                    "runner_id": runner_id,
                },
                sort_keys=True,
            )
        )
        return 0 if outcome.event in {
            EventType.GLOBAL_STOP,
            EventType.MAX_POSITION_STOP,
        } else 1
    except legacy.CanonicalDecisionProcessingError as error:
        final_reason = str(error)
        if logger is not None:
            logger.emit_event(
                EventType.BLOCKER,
                blocker_category="ENGINEERING_BLOCKER",
                blocker_code="CANONICAL_DECISION_PROCESSING_FAILED",
                position=(snapshot.next_due_position if snapshot is not None else None),
                role="DURABLE_RECONCILIATION",
                reason=str(error),
            )
        print(f"BLOCKER: {error}", file=sys.stderr)
        return 1
    except RunnerError as error:
        final_reason = str(error)
        if logger is not None:
            logger.emit_event(
                EventType.ERROR if preflight_complete else EventType.PRE_RUN_BLOCKER,
                reason=str(error),
            )
        prefix = "ERROR" if preflight_complete else "PRE_RUN_BLOCKER"
        print(f"{prefix}: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        final_reason = "keyboard interrupt received"
        if logger is not None:
            logger.emit_event(EventType.ERROR, reason=final_reason)
        print(f"ERROR: {final_reason}", file=sys.stderr)
        return 130
    except Exception as error:
        final_reason = f"UNEXPECTED_FAIL_CLOSED_ERROR: {type(error).__name__}: {error}"
        if logger is not None:
            logger.emit_event(EventType.ERROR, reason=final_reason)
        print(f"ERROR: {final_reason}", file=sys.stderr)
        return 1
    finally:
        heartbeat.stopped(final_reason)
        for handled_signal, previous in previous_handlers.items():
            signal.signal(handled_signal, previous)


if __name__ == "__main__":
    raise SystemExit(main())
