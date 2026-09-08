#!/usr/bin/env python3
"""Fail-closed external orchestration for Track A autonomous production.

The orchestrator reads only durable protocol, ledger, position-state, reviewer
assignment, and publication metadata.  Candidate semantics are handled only by
fresh role-specific Codex processes.  Semantic reviewer processes run inside a
filesystem capsule containing only assignment-authorized material.
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
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Protocol, Sequence
import uuid

from review_sandbox_network import (
    ReviewSandboxConfigurationError,
    resolve_resolver_mount_policy,
    reviewer_bwrap_prefix,
)


DEFAULT_WORKTREE = Path(
    "/home/anjum/Documents/research/correct-memory-study-worktrees/"
    "candidate-screening-v020-hybrid"
)
DEFAULT_RUNNER_ROOT = Path("/home/anjum/track-a-production-runner")
EXPECTED_BRANCH = "feat/candidate-screening-v020-hybrid-freeze"
AMENDMENT_RELATIVE_PATH = PurePosixPath(
    "benchmark-selection/screening/operational-amendments/"
    "prospective-autonomous-ai-review-v0.1"
)
CORRECTION_RELATIVE_PATH = PurePosixPath(
    "benchmark-selection/screening/operational-amendments/"
    "autonomous-runner-codex-cli-compatibility-v0.1"
)
PROVIDER_CORRECTION_RELATIVE_PATH = PurePosixPath(
    "benchmark-selection/screening/operational-amendments/"
    "autonomous-ai-review-structured-output-correction-v0.1"
)
RUN_RELATIVE_PATH = PurePosixPath(
    "benchmark-selection/screening/runs/v0.2.0/"
    "run-09fafb41e8c4c29e4774ff9cc98027ed0630c2f4422ac801ea19bf19fdd24879"
)
QUEUE_RELATIVE_PATH = PurePosixPath(
    "benchmark-selection/screening/runs/v0.1.19/"
    "production-queue-ab343bd1fb0d631057b7c4a5b6b979f534a8afdc5d50d1aa66ce8e0bc9d8ea13/"
    "screening-queue.json"
)
QUEUE_MANIFEST_RELATIVE_PATH = QUEUE_RELATIVE_PATH.with_name("queue-manifest.json")
DEFAULT_MAX_POSITIONS = 25
DEFAULT_CODEX_MODEL = "gpt-5.6-sol"
MAX_ROLE_TRANSITIONS_PER_POSITION = 12
SAFE_RETRY_LIMIT = 1
EFFECTIVE_POSITION = 22
AMENDMENT_ID = "candidate-screening-v0.2.0-prospective-autonomous-ai-review-v0.1"
CORRECTION_ID = (
    "candidate-screening-v0.2.0-autonomous-runner-codex-cli-compatibility-v0.1"
)
UNATTENDED_CODEX_OPTION = "--dangerously-bypass-approvals-and-sandbox"
AI_OUTPUT_SCHEMA = "ai-review-output.schema.json"
AI_PROVIDER_OUTPUT_SCHEMA = "ai-review-provider-output.schema.json"
AI_PROVIDER_COMPATIBILITY_PROFILE = "provider-compatibility-profile.json"
AI_DECISION_SCHEMA_VERSION = "candidate-screening-ai-review-decision-v0.1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
POSITION_SEGMENT_RE = re.compile(r"/(?:positions|records)/(\d{8})(?:/|\.json$)")
FORBIDDEN_SECRET_ENV_RE = re.compile(
    r"(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|COOKIE)", re.IGNORECASE
)
FORBIDDEN_B_PATH_FRAGMENTS = (
    "reviewer-a",
    "ai-reviewer-a",
    "combined-review",
    "family-feasibility",
    "family-recipe",
    "/records/",
)
FROZEN_REVIEW_INTERFACE_PATHS = frozenset(
    {
        "benchmark-selection/screening/protocol/v0.2.0/PROTOCOL.md",
        "benchmark-selection/screening/protocol/v0.2.0/review-policy.json",
        "src/cmpilot/tptm/canonical.py",
        "src/cmpilot/tptm/cli.py",
        "src/cmpilot/tptm/codes.py",
        "src/cmpilot/tptm/review.py",
        "src/cmpilot/tptm/rules/trust_predicates.json",
        "src/cmpilot/tptm/rules/witnesses.json",
        "src/cmpilot/tptm/schemas/review-decision-v1.schema.json",
    }
)
TERMINAL_AUTOCONTINUE_STATES = frozenset(
    {
        "AUTO_MECHANICAL_REJECT",
        "OUT_OF_SCOPE_UNSUPPORTED",
        "ADMIN_REPOSITORY_ANCHOR_LIMIT",
        "REVIEW_REJECT",
        "FAMILY_CONSTRUCTION_FAILED",
        "FAMILY_VALIDATION_FAILED",
        "VALIDATED_NOT_ADMITTED_CATEGORY_CAP",
        "VALIDATED_NOT_ADMITTED_REPOSITORY_GROUP",
        "ADMIT_FINAL",
    }
)


class RunnerError(RuntimeError):
    """A condition the autonomous runner cannot affirmatively prove safe."""


class ProviderEvidenceReferenceContractError(RunnerError):
    """The assignment-bound reviewer evidence vocabulary failed closed."""


class CanonicalDecisionProcessingError(RunnerError):
    """A validated typed review decision could not enter canonical JSON."""


class Classification(StrEnum):
    AUTO_CONTINUE = "AUTO_CONTINUE"
    AI_REVIEW_A = "AI_REVIEW_A"
    AI_REVIEW_B = "AI_REVIEW_B"
    COMBINATION_CONTINUATION = "COMBINATION_CONTINUATION"
    BLOCKER = "BLOCKER"
    GLOBAL_STOP = "GLOBAL_STOP"
    MAX_POSITION_STOP = "MAX_POSITION_STOP"
    ERROR = "ERROR"
    DRY_RUN = "DRY_RUN"


class Phase(StrEnum):
    NEED_CONTROLLER = "NEED_CONTROLLER"
    NEED_REVIEW_A = "NEED_REVIEW_A"
    NEED_CONTINUATION = "NEED_CONTINUATION"
    NEED_REVIEW_B = "NEED_REVIEW_B"
    NEED_COMBINATION = "NEED_COMBINATION"
    BLOCKER = "BLOCKER"


class Role(StrEnum):
    POSITION_CONTROLLER = "POSITION_CONTROLLER"
    AI_FIRST_REVIEW = "AI_FIRST_REVIEW"
    CONTINUATION_CONTROLLER = "CONTINUATION_CONTROLLER"
    AI_SECOND_REVIEW = "AI_SECOND_REVIEW"
    COMBINATION_CONTINUATION_CONTROLLER = "COMBINATION_CONTINUATION_CONTROLLER"


PHASE_ROLE = {
    Phase.NEED_CONTROLLER: Role.POSITION_CONTROLLER,
    Phase.NEED_REVIEW_A: Role.AI_FIRST_REVIEW,
    Phase.NEED_CONTINUATION: Role.CONTINUATION_CONTROLLER,
    Phase.NEED_REVIEW_B: Role.AI_SECOND_REVIEW,
    Phase.NEED_COMBINATION: Role.COMBINATION_CONTINUATION_CONTROLLER,
}

ROLE_CLASSIFICATION = {
    Role.POSITION_CONTROLLER: Classification.AUTO_CONTINUE,
    Role.AI_FIRST_REVIEW: Classification.AI_REVIEW_A,
    Role.CONTINUATION_CONTROLLER: Classification.COMBINATION_CONTINUATION,
    Role.AI_SECOND_REVIEW: Classification.AI_REVIEW_B,
    Role.COMBINATION_CONTINUATION_CONTROLLER: Classification.COMBINATION_CONTINUATION,
}


@dataclass(frozen=True, slots=True)
class Snapshot:
    head: str
    records_published: int
    successor_positions_processed: int
    historical_unique_opened_anchors: int
    global_unique_opened_anchors: int
    final: int
    categories_represented: int
    next_due_position: int
    global_action: str


@dataclass(frozen=True, slots=True)
class DurableToken:
    head: str
    porcelain_sha256: str
    ledger_sha256: str
    position_tree_sha256: str


@dataclass(frozen=True, slots=True)
class RoleExecution:
    role: Role
    position: int
    invocation_id: str
    started_at_utc: str
    ended_at_utc: str
    exit_code: int
    stdout: str
    stderr: str
    prompt: str
    prompt_sha256: str
    codex_thread_id: str | None = None
    model_identifier: str | None = None
    profile_identifier: str | None = None
    last_message_path: Path | None = None
    infrastructure_failure: str | None = None
    partial_decision_present: bool = False


@dataclass(frozen=True, slots=True)
class RunOutcome:
    classification: Classification
    positions_completed: int
    next_due_position: int
    message: str


class DurableRepository(Protocol):
    def snapshot(self) -> Snapshot: ...

    def phase(self, position: int) -> Phase: ...

    def durable_token(self, position: int) -> DurableToken: ...

    def accept_execution(
        self, execution: RoleExecution, before: DurableToken
    ) -> None: ...

    def last_terminal_processing_state(self, position: int) -> str: ...

    def blocker_reason(self, position: int) -> str: ...


class RoleExecutor(Protocol):
    def execute(
        self, role: Role, position: int, expected_head: str
    ) -> RoleExecution: ...


class EventLogger(Protocol):
    def emit(self, classification: Classification, **fields: Any) -> None: ...


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_review_projection_bytes(value: Any) -> bytes:
    """Use the repository's scientific canonical JSON boundary for review payloads."""

    try:
        from cmpilot.tptm.canonical import (  # type: ignore
            CanonicalizationError,
            canonical_json_bytes as canonical_semantic_json_bytes,
        )

        return canonical_semantic_json_bytes(value)
    except CanonicalizationError as error:
        raise CanonicalDecisionProcessingError(
            f"canonical AI reviewer decision serialization failed: {error}"
        ) from error


def canonical_decision_processing_allows_retry() -> bool:
    """Deterministic canonical-decision failures never use reviewer/network retry."""

    return False


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file():
        raise RunnerError(f"required regular JSON file is absent: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RunnerError(f"cannot parse JSON artifact: {path}") from error


def write_exclusive(path: Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)


def atomic_replace_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def subprocess_text(
    command: Sequence[str], *, cwd: Path, check: bool = True
) -> str:
    process = subprocess.run(
        list(command),
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=sanitized_environment(),
    )
    if check and process.returncode != 0:
        detail = process.stderr.strip() or process.stdout.strip()
        raise RunnerError(f"command failed ({command[0]}): {detail}")
    return process.stdout


def sanitized_environment() -> dict[str, str]:
    allowed = {
        "CODEX_HOME",
        "DBUS_SESSION_BUS_ADDRESS",
        "GIT_AUTHOR_EMAIL",
        "GIT_AUTHOR_NAME",
        "GIT_COMMITTER_EMAIL",
        "GIT_COMMITTER_NAME",
        "HOME",
        "LANG",
        "LC_ALL",
        "LOGNAME",
        "PATH",
        "SSH_AUTH_SOCK",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "TERM",
        "TMPDIR",
        "USER",
        "XDG_CONFIG_HOME",
        "XDG_RUNTIME_DIR",
    }
    return {
        key: value
        for key, value in os.environ.items()
        if key in allowed and not FORBIDDEN_SECRET_ENV_RE.search(key)
    }


class StateMachine:
    """Metadata-only sequential orchestration shared by production and fakes."""

    def __init__(
        self,
        repository: DurableRepository,
        executor: RoleExecutor,
        logger: EventLogger,
    ) -> None:
        self.repository = repository
        self.executor = executor
        self.logger = logger

    def run(self, max_positions: int) -> RunOutcome:
        if isinstance(max_positions, bool) or max_positions <= 0:
            raise RunnerError("--max-positions must be a positive integer")
        completed = 0
        role_transitions: dict[int, int] = {}
        while True:
            snapshot = self.repository.snapshot()
            if snapshot.global_action != "CONTINUE":
                self.logger.emit(
                    Classification.GLOBAL_STOP,
                    next_due_position=snapshot.next_due_position,
                    global_action=snapshot.global_action,
                )
                return RunOutcome(
                    Classification.GLOBAL_STOP,
                    completed,
                    snapshot.next_due_position,
                    f"frozen global action is {snapshot.global_action}",
                )
            if completed >= max_positions:
                self.logger.emit(
                    Classification.MAX_POSITION_STOP,
                    next_due_position=snapshot.next_due_position,
                    positions_completed=completed,
                )
                return RunOutcome(
                    Classification.MAX_POSITION_STOP,
                    completed,
                    snapshot.next_due_position,
                    "configured operational position bound reached",
                )

            position = snapshot.next_due_position
            transitions = role_transitions.get(position, 0)
            if transitions >= MAX_ROLE_TRANSITIONS_PER_POSITION:
                return self._block(
                    completed,
                    position,
                    "role-transition ceiling reached without terminal publication",
                )
            phase = self.repository.phase(position)
            if phase is Phase.BLOCKER:
                return self._block(
                    completed, position, self.repository.blocker_reason(position)
                )
            role = PHASE_ROLE[phase]
            before = self.repository.durable_token(position)
            attempts = 0
            while True:
                execution = self.executor.execute(role, position, snapshot.head)
                self.logger.emit(
                    ROLE_CLASSIFICATION[role],
                    position=position,
                    role=role.value,
                    invocation_id=execution.invocation_id,
                    prompt_sha256=execution.prompt_sha256,
                    exit_code=execution.exit_code,
                )
                if execution.exit_code == 0:
                    break
                after_failure = self.repository.durable_token(position)
                if after_failure == before and attempts < SAFE_RETRY_LIMIT:
                    attempts += 1
                    continue
                classification = (
                    "CODEX_PRE_WRITE_FAILURE_RETRY_EXHAUSTED"
                    if after_failure == before
                    else "CODEX_FAILURE_AFTER_POSSIBLE_DURABLE_CHANGE"
                )
                self.logger.emit(
                    Classification.ERROR,
                    position=position,
                    role=role.value,
                    reason=classification,
                )
                return RunOutcome(
                    Classification.ERROR, completed, position, classification
                )

            try:
                self.repository.accept_execution(execution, before)
            except RunnerError as error:
                self.logger.emit(
                    Classification.BLOCKER,
                    position=position,
                    role=role.value,
                    reason=str(error),
                )
                return RunOutcome(
                    Classification.BLOCKER, completed, position, str(error)
                )

            role_transitions[position] = transitions + 1
            after = self.repository.snapshot()
            if after.records_published == snapshot.records_published + 1:
                if (
                    after.next_due_position != position + 1
                    or after.successor_positions_processed
                    != snapshot.successor_positions_processed + 1
                ):
                    return self._block(
                        completed,
                        position,
                        "terminal publication did not advance exactly one position",
                    )
                terminal_state = self.repository.last_terminal_processing_state(
                    position
                )
                if terminal_state == "ANALYSIS_ERROR":
                    return self._block(
                        completed,
                        after.next_due_position,
                        "ANALYSIS_ERROR terminal publication requires fail-closed stop",
                    )
                if terminal_state not in TERMINAL_AUTOCONTINUE_STATES:
                    return self._block(
                        completed,
                        after.next_due_position,
                        f"unrecognized terminal processing state: {terminal_state}",
                    )
                completed += 1
                self.logger.emit(
                    Classification.AUTO_CONTINUE,
                    position=position,
                    terminal_processing_state=terminal_state,
                    next_due_position=after.next_due_position,
                )
            elif after.records_published != snapshot.records_published:
                return self._block(
                    completed,
                    position,
                    "role changed published-record count by more than one",
                )

    def _block(self, completed: int, position: int, reason: str) -> RunOutcome:
        self.logger.emit(
            Classification.BLOCKER, position=position, reason=reason
        )
        return RunOutcome(Classification.BLOCKER, completed, position, reason)


class AppendOnlyLogger:
    def __init__(self, root: Path, runner_id: str) -> None:
        self.root = root
        self.runner_id = runner_id
        self.run_dir = root / "logs" / runner_id
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.events_path = self.run_dir / "events.jsonl"

    def emit(self, classification: Classification, **fields: Any) -> None:
        event = {
            "schema": "track-a-runner-event-v0.1",
            "runner_id": self.runner_id,
            "timestamp_utc": utc_now(),
            "classification": classification.value,
            **fields,
        }
        descriptor = os.open(
            self.events_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600
        )
        try:
            os.write(descriptor, canonical_json_bytes(event) + b"\n")
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def role_attempt_dir(
        self, position: int, role: Role, attempt: int
    ) -> Path:
        role_names = {
            Role.POSITION_CONTROLLER: "controller",
            Role.AI_FIRST_REVIEW: "reviewer-a",
            Role.CONTINUATION_CONTROLLER: "continuation",
            Role.AI_SECOND_REVIEW: "reviewer-b",
            Role.COMBINATION_CONTINUATION_CONTROLLER: "combination-continuation",
        }
        path = (
            self.run_dir
            / f"position-{position:08d}"
            / role_names[role]
            / f"attempt-{attempt:02d}"
        )
        path.mkdir(parents=True, exist_ok=False)
        return path


class ProductionRepository:
    def __init__(
        self,
        worktree: Path,
        runner_root: Path,
        state_path: Path,
        logger: AppendOnlyLogger,
    ) -> None:
        self.worktree = worktree.resolve()
        self.runner_root = runner_root.resolve()
        self.state_path = state_path
        self.logger = logger
        self.state = self._load_state()
        self.run_path = self.worktree / RUN_RELATIVE_PATH
        self.amendment_path = self.worktree / AMENDMENT_RELATIVE_PATH
        self.correction_path = self.worktree / CORRECTION_RELATIVE_PATH
        self.provider_correction_path = (
            self.worktree / PROVIDER_CORRECTION_RELATIVE_PATH
        )
        self.ledger_path = self.run_path / "ledger.json"
        self.ledger_sidecar_path = self.run_path / "ledger.json.sha256"
        self._last_snapshot: Snapshot | None = None

    def _load_state(self) -> dict[str, Any]:
        value = read_json(self.state_path)
        required = {
            "schema",
            "worktree",
            "branch",
            "freeze_head",
            "expected_head",
            "amendment_manifest_sha256",
            "baseline_porcelain",
        }
        if not isinstance(value, dict) or set(value) != required:
            raise RunnerError("external runner state fields are not exact")
        if value["schema"] != "track-a-production-runner-state-v0.1":
            raise RunnerError("external runner state schema differs")
        if Path(value["worktree"]).resolve() != self.worktree:
            raise RunnerError("runner state worktree identity differs")
        if value["branch"] != EXPECTED_BRANCH:
            raise RunnerError("runner state branch identity differs")
        for key in ("freeze_head", "expected_head"):
            if not re.fullmatch(r"[0-9a-f]{40}", value[key]):
                raise RunnerError(f"runner state {key} is invalid")
        if not SHA256_RE.fullmatch(value["amendment_manifest_sha256"]):
            raise RunnerError("runner state amendment manifest digest is invalid")
        if not isinstance(value["baseline_porcelain"], list) or any(
            not isinstance(item, str) for item in value["baseline_porcelain"]
        ):
            raise RunnerError("runner baseline porcelain state is invalid")
        return value

    def preflight(self, *, dry_run: bool, codex_bin: Path | None) -> Snapshot:
        if self.worktree != Path(self.state["worktree"]).resolve():
            raise RunnerError("production worktree path differs")
        if self.runner_root == self.worktree or self.worktree in self.runner_root.parents:
            raise RunnerError("runner root must remain outside the production worktree")
        branch = self._git("branch", "--show-current").strip()
        if branch != EXPECTED_BRANCH:
            raise RunnerError(f"production branch differs: {branch}")
        head = self._git("rev-parse", "HEAD").strip()
        if head != self.state["expected_head"]:
            raise RunnerError(
                f"unexpected HEAD: expected {self.state['expected_head']}, observed {head}"
            )
        self._verify_clean_expectations()
        amendment = self._verify_amendment()
        if not dry_run:
            if codex_bin is None:
                raise RunnerError("Codex executable is unavailable")
            observed_version = subprocess_text(
                [str(codex_bin), "--version"], cwd=self.worktree
            ).strip()
            expected_version = amendment["external_runner"]["codex_cli_version"]
            if observed_version != expected_version:
                raise RunnerError(
                    f"Codex CLI version mismatch: expected {expected_version}, "
                    f"observed {observed_version}"
                )
        return self.snapshot()

    def _verify_amendment(self) -> dict[str, Any]:
        manifest_path = self.amendment_path / "freeze-manifest.json"
        manifest_sidecar = self.amendment_path / "freeze-manifest.json.sha256"
        self._verify_sidecar(manifest_path, manifest_sidecar)
        manifest_sha256 = sha256_file(manifest_path)
        manifest = read_json(manifest_path)
        if (
            not isinstance(manifest, dict)
            or manifest.get("amendment_id") != AMENDMENT_ID
            or manifest.get("effective_position") != EFFECTIVE_POSITION
        ):
            raise RunnerError("amendment freeze identity differs")
        for artifact in manifest.get("artifacts", []):
            relative = self._safe_relative(artifact.get("path"))
            path = self.worktree / relative
            if path.is_symlink() or not path.is_file():
                raise RunnerError(f"frozen amendment artifact absent: {relative}")
            if sha256_file(path) != artifact.get("sha256"):
                raise RunnerError(f"frozen amendment artifact mismatch: {relative}")
        amendment_path = self.amendment_path / "operational-amendment.json"
        self._verify_sidecar(
            amendment_path, self.amendment_path / "operational-amendment.json.sha256"
        )
        amendment_sha256 = sha256_file(amendment_path)
        amendment = read_json(amendment_path)
        if (
            amendment.get("amendment_id") != AMENDMENT_ID
            or amendment.get("effective_position") != EFFECTIVE_POSITION
            or amendment.get("historical_positions") != {"first": 1, "last": 21}
            or amendment.get("scientifically_neutral") is not False
        ):
            raise RunnerError("prospective amendment protocol phase differs")

        correction_manifest_path = self.correction_path / "freeze-manifest.json"
        self._verify_sidecar(
            correction_manifest_path,
            self.correction_path / "freeze-manifest.json.sha256",
        )
        if (
            sha256_file(correction_manifest_path)
            != self.state["amendment_manifest_sha256"]
        ):
            raise RunnerError("runner state and effective freeze manifest differ")
        correction_manifest = read_json(correction_manifest_path)
        if (
            not isinstance(correction_manifest, dict)
            or correction_manifest.get("correction_id") != CORRECTION_ID
            or correction_manifest.get("effective_from_position")
            != EFFECTIVE_POSITION
            or correction_manifest.get("scientific_methodology_changed") is not False
        ):
            raise RunnerError("runner correction freeze identity differs")
        for artifact in correction_manifest.get("artifacts", []):
            relative = self._safe_relative(artifact.get("path"))
            path = self.worktree / relative
            if path.is_symlink() or not path.is_file():
                raise RunnerError(f"frozen correction artifact absent: {relative}")
            if sha256_file(path) != artifact.get("sha256"):
                raise RunnerError(f"frozen correction artifact mismatch: {relative}")

        correction_path = self.correction_path / "operational-amendment.json"
        self._verify_sidecar(
            correction_path,
            self.correction_path / "operational-amendment.json.sha256",
        )
        correction = read_json(correction_path)
        if (
            not isinstance(correction, dict)
            or correction.get("correction_id") != CORRECTION_ID
            or correction.get("effective_from_position") != EFFECTIVE_POSITION
            or correction.get("scientific_methodology_changed") is not False
            or correction.get("reviewer_authority_changed_from_base_amendment")
            is not False
            or correction.get("external_runner_only") is not True
        ):
            raise RunnerError("runner correction operational scope differs")

        base_reference = {
            "amendment_id": AMENDMENT_ID,
            "amendment_version": "v0.1",
            "path": str(AMENDMENT_RELATIVE_PATH),
            "freeze_manifest_sha256": manifest_sha256,
            "operational_amendment_sha256": amendment_sha256,
            "effective_position": EFFECTIVE_POSITION,
        }
        if (
            correction_manifest.get("base_amendment") != base_reference
            or correction.get("base_amendment") != base_reference
        ):
            raise RunnerError("runner correction base amendment differs")

        frozen_external = manifest.get("external_runner_artifacts")
        if (
            not isinstance(frozen_external, list)
            or amendment["external_runner"]["artifacts"] != frozen_external
            or correction_manifest.get("superseded_external_runner_artifacts")
            != frozen_external
            or correction.get("old_external_runner_artifacts") != frozen_external
        ):
            raise RunnerError("runner correction superseded hashes differ")
        corrected_external = correction.get("corrected_external_runner_artifacts")
        if (
            not isinstance(corrected_external, list)
            or correction_manifest.get("external_runner_artifacts")
            != corrected_external
        ):
            raise RunnerError("runner correction effective hashes differ")
        for artifact in corrected_external:
            path = Path(artifact["path"])
            if path.is_symlink() or not path.is_file():
                raise RunnerError(f"external runner artifact absent: {path}")
            if sha256_file(path) != artifact["sha256"]:
                raise RunnerError(f"external runner hash mismatch: {path}")
        base = amendment["preserved_base_authority"]
        queue_path = self.worktree / QUEUE_RELATIVE_PATH
        queue_manifest_path = self.worktree / QUEUE_MANIFEST_RELATIVE_PATH
        if queue_path.is_symlink() or not queue_path.is_file():
            raise RunnerError("sealed queue path is not a regular file")
        if queue_manifest_path.is_symlink() or not queue_manifest_path.is_file():
            raise RunnerError("sealed queue manifest path is not a regular file")
        if sha256_file(queue_path) != base["queue_sha256"]:
            raise RunnerError("sealed queue identity mismatch")
        if (
            sha256_file(queue_manifest_path)
            != base["queue_manifest_sha256"]
        ):
            raise RunnerError("sealed queue manifest identity mismatch")
        return amendment

    def _verify_sidecar(self, path: Path, sidecar: Path) -> None:
        digest = sha256_file(path)
        expected = f"{digest}  {path.name}\n"
        if sidecar.is_symlink() or not sidecar.is_file():
            raise RunnerError(f"SHA-256 sidecar absent: {sidecar}")
        if sidecar.read_text(encoding="ascii") != expected:
            raise RunnerError(f"SHA-256 sidecar mismatch: {sidecar}")

    def _verify_clean_expectations(self) -> None:
        if self._git_status() != self.state["baseline_porcelain"]:
            raise RunnerError("tracked worktree/index or baseline untracked state differs")
        if self._git("diff", "--name-only").strip():
            raise RunnerError("tracked worktree is modified")
        if self._git("diff", "--cached", "--name-only").strip():
            raise RunnerError("index is modified")

    def _git_status(self) -> list[str]:
        output = self._git(
            "status", "--porcelain=v1", "--untracked-files=normal"
        )
        return output.splitlines()

    def _git(self, *arguments: str, check: bool = True) -> str:
        return subprocess_text(
            ["git", *arguments], cwd=self.worktree, check=check
        )

    def snapshot(self) -> Snapshot:
        head = self._git("rev-parse", "HEAD").strip()
        if head != self.state["expected_head"]:
            raise RunnerError("HEAD changed outside an accepted role transition")
        self._verify_clean_expectations()
        self._verify_sidecar(self.ledger_path, self.ledger_sidecar_path)
        ledger = read_json(self.ledger_path)
        if not isinstance(ledger, dict):
            raise RunnerError("ledger must be an object")
        records_published = ledger.get("records_published")
        if isinstance(records_published, bool) or not isinstance(
            records_published, int
        ):
            raise RunnerError("ledger records_published is invalid")
        record_paths = ledger.get("record_paths")
        if not isinstance(record_paths, list) or len(record_paths) != records_published:
            raise RunnerError("ledger record-path sequence differs")
        records = []
        for position in range(1, records_published + 1):
            path = self.run_path / "records" / f"{position:08d}.json"
            records.append(read_json(path))
        self._replay_ledger(ledger, records)
        for position in range(EFFECTIVE_POSITION, records_published + 1):
            self._verify_amended_terminal_record(position, records[position - 1])
        state = ledger.get("state")
        if not isinstance(state, dict):
            raise RunnerError("ledger state is absent")
        snapshot = Snapshot(
            head=head,
            records_published=state["records_published"],
            successor_positions_processed=state["successor_positions_processed"],
            historical_unique_opened_anchors=state[
                "historical_unique_opened_anchors"
            ],
            global_unique_opened_anchors=state["global_unique_opened_anchors"],
            final=state["FINAL"],
            categories_represented=state["trust_categories_represented"],
            next_due_position=state["next_due_position"],
            global_action=state["global_action"],
        )
        if (
            snapshot.records_published != records_published
            or snapshot.successor_positions_processed != records_published
            or snapshot.next_due_position != records_published + 1
            or snapshot.historical_unique_opened_anchors != 2
        ):
            raise RunnerError("ledger sequential accounting differs")
        self._last_snapshot = snapshot
        return snapshot

    def _replay_ledger(
        self, ledger: Mapping[str, Any], records: Sequence[Mapping[str, Any]]
    ) -> None:
        source_root = str(self.worktree / "src")
        inserted = source_root not in sys.path
        if inserted:
            sys.path.insert(0, source_root)
        try:
            from cmpilot.candidate_screening_v020 import (  # type: ignore
                ProtocolInvariantError,
                validate_published_successor_ledger,
            )

            try:
                validate_published_successor_ledger(ledger, records)
            except ProtocolInvariantError as error:
                raise RunnerError(f"record replay failure: {error}") from error
        finally:
            if inserted:
                sys.path.remove(source_root)

    def phase(self, position: int) -> Phase:
        if position < EFFECTIVE_POSITION:
            raise RunnerError("autonomous amendment cannot control a historical position")
        record = self.run_path / "records" / f"{position:08d}.json"
        if record.exists():
            raise RunnerError("due position already has an inconsistent record")
        position_path = self.position_path(position)
        if not position_path.exists():
            return Phase.NEED_CONTROLLER
        if position_path.is_symlink() or not position_path.is_dir():
            raise RunnerError("current position runtime path is not a regular directory")
        if (position_path / "autonomous-blocker.json").exists():
            return Phase.BLOCKER
        decision_a = position_path / "ai-reviewer-a-decision.json"
        assignment_a = position_path / "ai-reviewer-a-assignment.json"
        decision_b = position_path / "ai-reviewer-b-decision.json"
        assignment_b = self.latest_b_assignment(position)
        if decision_a.exists():
            self.validate_ai_decision(decision_a, Role.AI_FIRST_REVIEW)
            if decision_b.exists():
                self.validate_ai_decision(decision_b, Role.AI_SECOND_REVIEW)
                return Phase.NEED_COMBINATION
            if assignment_b is not None:
                self.validate_assignment(assignment_b, Role.AI_SECOND_REVIEW)
                reviewer_b_required, _, _ = self.reviewer_b_requirement(position)
                if not reviewer_b_required:
                    raise RunnerError(
                        "Reviewer B assignment exists outside the frozen trigger"
                    )
                return Phase.NEED_REVIEW_B
            return Phase.NEED_CONTINUATION
        if assignment_a.exists():
            self.validate_assignment(assignment_a, Role.AI_FIRST_REVIEW)
            return Phase.NEED_REVIEW_A
        return Phase.BLOCKER

    def blocker_reason(self, position: int) -> str:
        blocker = self.position_path(position) / "autonomous-blocker.json"
        if blocker.exists():
            value = read_json(blocker)
            blocker_class = value.get("blocker_class", "AMBIGUOUS_BLOCKER")
            return f"{blocker_class}: durable autonomous blocker"
        return "missing frozen interface or ambiguous partial position state"

    def position_path(self, position: int) -> Path:
        return self.run_path / "positions" / f"{position:08d}"

    def latest_b_assignment(self, position: int) -> Path | None:
        root = self.position_path(position)
        candidates = []
        base = root / "ai-reviewer-b-assignment.json"
        if base.exists():
            candidates.append((0, base))
        for path in root.glob("ai-reviewer-b-assignment-[0-9][0-9][0-9][0-9].json"):
            number = int(path.stem.rsplit("-", 1)[-1])
            candidates.append((number, path))
        return max(candidates, default=(0, None), key=lambda item: item[0])[1]

    def durable_token(self, position: int) -> DurableToken:
        head = self._git("rev-parse", "HEAD").strip()
        porcelain = "\n".join(self._git_status()).encode("utf-8")
        ledger_digest = (
            sha256_file(self.ledger_path) if self.ledger_path.is_file() else "ABSENT"
        )
        position_path = self.position_path(position)
        rows: list[tuple[str, str]] = []
        if position_path.is_dir():
            for path in sorted(position_path.rglob("*")):
                if path.is_file() and not path.is_symlink():
                    rows.append(
                        (str(path.relative_to(position_path)), sha256_file(path))
                    )
                elif path.is_symlink():
                    rows.append((str(path.relative_to(position_path)), "SYMLINK"))
        return DurableToken(
            head=head,
            porcelain_sha256=sha256_bytes(porcelain),
            ledger_sha256=ledger_digest,
            position_tree_sha256=sha256_bytes(canonical_json_bytes(rows)),
        )

    def accept_execution(
        self, execution: RoleExecution, before: DurableToken
    ) -> None:
        if execution.role in {Role.AI_FIRST_REVIEW, Role.AI_SECOND_REVIEW}:
            self._accept_reviewer_execution(execution, before)
        else:
            self._accept_mutating_execution(execution, before)

    def _accept_mutating_execution(
        self, execution: RoleExecution, before: DurableToken
    ) -> None:
        after_head = self._git("rev-parse", "HEAD").strip()
        if after_head == before.head:
            raise RunnerError("successful controller produced no committed durable state")
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", before.head, after_head],
            cwd=self.worktree,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            env=sanitized_environment(),
        )
        if ancestor.returncode != 0:
            raise RunnerError("controller HEAD change is not a forward descendant")
        changed = self._git("diff", "--name-only", f"{before.head}..{after_head}")
        self._validate_changed_paths(execution.position, changed.splitlines())
        terminal_record = (
            self.run_path / "records" / f"{execution.position:08d}.json"
        )
        if execution.role is Role.CONTINUATION_CONTROLLER:
            reviewer_b_required, _, _ = self.reviewer_b_requirement(
                execution.position
            )
            assignment_b = self.latest_b_assignment(execution.position)
            if terminal_record.exists() and reviewer_b_required:
                raise RunnerError(
                    "continuation published terminal state despite required Reviewer B"
                )
            if assignment_b is not None and not reviewer_b_required:
                raise RunnerError("continuation created Reviewer B outside frozen trigger")
        self._accept_new_head(after_head)
        self._verify_clean_expectations()
        if not terminal_record.exists():
            current_phase = self.phase(execution.position)
            if current_phase is PHASE_FOR_ROLE(execution.role):
                raise RunnerError("controller did not advance the durable role phase")

    def _accept_reviewer_execution(
        self, execution: RoleExecution, before: DurableToken
    ) -> None:
        if self.durable_token(execution.position) != before:
            raise RunnerError("isolated reviewer unexpectedly changed production state")
        if execution.last_message_path is None:
            raise RunnerError("reviewer last-message artifact is absent")
        position_path = self.position_path(execution.position)
        if execution.role is Role.AI_FIRST_REVIEW:
            assignment_path = position_path / "ai-reviewer-a-assignment.json"
            decision_path = position_path / "ai-reviewer-a-decision.json"
            reviewer_role = "AI_FIRST_REVIEW"
            commit_role = "A"
        else:
            assignment_path = self.latest_b_assignment(execution.position)
            if assignment_path is None:
                raise RunnerError("Reviewer B assignment is absent")
            decision_path = position_path / "ai-reviewer-b-decision.json"
            reviewer_role = "AI_SECOND_REVIEW"
            commit_role = "B"
        assignment = self.validate_assignment(assignment_path, execution.role)
        semantic, projection_sha256 = self._project_provider_output(
            execution.last_message_path, assignment
        )
        if semantic["candidate_id"] != assignment["candidate_id"]:
            raise RunnerError("AI decision and assignment candidate identities differ")
        envelope: dict[str, Any] = {
            "schema_version": AI_DECISION_SCHEMA_VERSION,
            "amendment_id": AMENDMENT_ID,
            "protocol_version": "candidate-screening-v0.2.0",
            "effective_position": EFFECTIVE_POSITION,
            "queue_position": execution.position,
            "reviewer_type": "AI",
            "reviewer_role": reviewer_role,
            "authority": "AUTHORITATIVE_SEMANTIC_REVIEW",
            "assignment_path": str(assignment_path.relative_to(self.worktree)),
            "assignment_sha256": sha256_file(assignment_path),
            "review_packet_sha256": assignment["review_packet"][
                "review_packet_sha256"
            ],
            "review_packet_file_sha256": assignment["review_packet"]["file_sha256"],
            "prompt_sha256": execution.prompt_sha256,
            "semantic_projection_sha256": projection_sha256,
            "codex_provenance": {
                "codex_cli_version": self._amendment()["external_runner"][
                    "codex_cli_version"
                ],
                "model_identifier": execution.model_identifier,
                "profile_identifier": execution.profile_identifier,
                "runner_invocation_id": execution.invocation_id,
                "codex_thread_id": execution.codex_thread_id,
                "fresh_process": True,
                "resumed_or_forked": False,
                "started_at_utc": execution.started_at_utc,
                "ended_at_utc": execution.ended_at_utc,
            },
            "semantic_decision": semantic,
            "decision_sha256": "0" * 64,
        }
        envelope["decision_sha256"] = sha256_bytes(
            canonical_json_bytes(
                {key: value for key, value in envelope.items() if key != "decision_sha256"}
            )
        )
        if decision_path.exists():
            raise RunnerError("authoritative AI decision path already exists")
        write_exclusive(decision_path, canonical_json_bytes(envelope), mode=0o644)
        add = subprocess.run(
            ["git", "add", "--", str(decision_path.relative_to(self.worktree))],
            cwd=self.worktree,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            env=sanitized_environment(),
        )
        if add.returncode != 0:
            raise RunnerError("AI decision created but git add failed; reconciliation required")
        commit = subprocess.run(
            [
                "git",
                "commit",
                "-m",
                f"Record position {execution.position} authoritative AI Reviewer {commit_role} decision",
            ],
            cwd=self.worktree,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            env=sanitized_environment(),
        )
        if commit.returncode != 0:
            raise RunnerError("AI decision created but commit failed; reconciliation required")
        after_head = self._git("rev-parse", "HEAD").strip()
        self._validate_changed_paths(
            execution.position,
            self._git("diff", "--name-only", f"{before.head}..{after_head}").splitlines(),
        )
        self._accept_new_head(after_head)
        self._verify_clean_expectations()

    def _accept_new_head(self, head: str) -> None:
        updated = dict(self.state)
        updated["expected_head"] = head
        atomic_replace_json(self.state_path, updated)
        self.state = updated

    def _validate_changed_paths(self, position: int, changed: Sequence[str]) -> None:
        prefix = f"{RUN_RELATIVE_PATH}/positions/{position:08d}/"
        record = f"{RUN_RELATIVE_PATH}/records/{position:08d}.json"
        ledger = f"{RUN_RELATIVE_PATH}/ledger.json"
        ledger_sidecar = f"{RUN_RELATIVE_PATH}/ledger.json.sha256"
        allowed_exact = {record, ledger, ledger_sidecar}
        if not changed:
            raise RunnerError("role commit contains no changed paths")
        for path in changed:
            if path in allowed_exact or path.startswith(prefix):
                continue
            raise RunnerError(f"role changed an unauthorized path: {path}")

    def _amendment(self) -> dict[str, Any]:
        value = read_json(self.amendment_path / "operational-amendment.json")
        if not isinstance(value, dict):
            raise RunnerError("amendment must be an object")
        return value

    def validate_assignment(self, path: Path, role: Role) -> dict[str, Any]:
        value = read_json(path)
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
            "candidate_id",
            "review_packet",
            "permitted_evidence_paths",
            "permitted_evidence_sha256",
            "permitted_interface_paths",
            "permitted_interface_sha256",
            "decision_output_path",
            "prohibited_information_boundary",
            "terminal_record_published",
            "ledger_updated",
        }
        if not isinstance(value, dict) or set(value) != required:
            raise RunnerError("AI reviewer assignment fields are not exact")
        expected_role = (
            "AI_FIRST_REVIEW" if role is Role.AI_FIRST_REVIEW else "AI_SECOND_REVIEW"
        )
        try:
            expected_position = int(path.parent.name)
        except ValueError as error:
            raise RunnerError("AI assignment position path is invalid") from error
        if (
            value["schema_version"] != "candidate-screening-ai-review-assignment-v0.1"
            or value["amendment_id"] != AMENDMENT_ID
            or value["protocol_version"] != "candidate-screening-v0.2.0"
            or value["status"] != "AWAITING_AUTHORITATIVE_AI_REVIEW"
            or value["queue_position"] != expected_position
            or expected_position < EFFECTIVE_POSITION
            or value["reviewer_type"] != "AI"
            or value["reviewer_role"] != expected_role
            or value["authoritative"] is not True
            or value["required_execution_boundary"]
            != "FRESH_ONE_SHOT_CODEX_PROCESS"
            or value["terminal_record_published"] is not False
            or value["ledger_updated"] is not False
            or not isinstance(value["candidate_id"], str)
            or not value["candidate_id"]
        ):
            raise RunnerError("AI reviewer assignment authority differs")
        packet = value["review_packet"]
        if not isinstance(packet, dict) or set(packet) != {
            "path",
            "review_packet_sha256",
            "file_sha256",
        }:
            raise RunnerError("review packet assignment identity differs")
        if not SHA256_RE.fullmatch(packet["review_packet_sha256"]) or not SHA256_RE.fullmatch(
            packet["file_sha256"]
        ):
            raise RunnerError("review packet SHA-256 identity is invalid")
        evidence_paths = value["permitted_evidence_paths"]
        interface_paths = value["permitted_interface_paths"]
        if (
            not isinstance(evidence_paths, list)
            or evidence_paths != sorted(set(evidence_paths))
            or not isinstance(interface_paths, list)
            or interface_paths != sorted(set(interface_paths))
        ):
            raise RunnerError("assignment permitted paths must be unique and ordered")
        if role is Role.AI_SECOND_REVIEW:
            serialized_paths = "\n".join(evidence_paths + interface_paths).lower()
            if any(fragment in serialized_paths for fragment in FORBIDDEN_B_PATH_FRAGMENTS):
                raise RunnerError("Reviewer B assignment includes prohibited A/outcome material")
        if packet["path"] not in evidence_paths:
            raise RunnerError("review packet is outside permitted evidence")
        self._validate_path_hash_map(
            evidence_paths, value["permitted_evidence_sha256"], expected_position
        )
        self._validate_path_hash_map(
            interface_paths, value["permitted_interface_sha256"], expected_position
        )
        if set(interface_paths) != FROZEN_REVIEW_INTERFACE_PATHS:
            raise RunnerError("review assignment frozen interface allowlist differs")
        expected_packet_path = str(
            RUN_RELATIVE_PATH
            / "positions"
            / f"{expected_position:08d}"
            / "review-packet.json"
        )
        if packet["path"] != expected_packet_path:
            raise RunnerError("review packet is not the current-position packet")
        for evidence_path in evidence_paths:
            if evidence_path == expected_packet_path:
                continue
            if not (
                evidence_path.startswith("benchmark-selection/discovery/runs/")
                and "/raw/sha256/" in evidence_path
            ):
                raise RunnerError("review evidence exceeds the historical bounded form")
        packet_path = self.worktree / self._safe_relative(packet["path"])
        if sha256_file(packet_path) != packet["file_sha256"]:
            raise RunnerError("review packet file hash differs")
        output_relative = self._safe_relative(value["decision_output_path"])
        expected_output = self.position_path(expected_position) / (
            "ai-reviewer-a-decision.json"
            if role is Role.AI_FIRST_REVIEW
            else "ai-reviewer-b-decision.json"
        )
        if self.worktree / output_relative != expected_output:
            raise RunnerError("AI reviewer decision output path differs")
        if role is Role.AI_SECOND_REVIEW:
            forbidden = value["prohibited_information_boundary"]
            expected_forbidden = {
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
            if forbidden != expected_forbidden:
                raise RunnerError("Reviewer B prohibited-information boundary differs")
            assignment_a_path = self.position_path(expected_position) / (
                "ai-reviewer-a-assignment.json"
            )
            assignment_a = self.validate_assignment(
                assignment_a_path, Role.AI_FIRST_REVIEW
            )
            for key in (
                "candidate_id",
                "review_packet",
                "permitted_evidence_paths",
                "permitted_evidence_sha256",
                "permitted_interface_paths",
                "permitted_interface_sha256",
            ):
                if value[key] != assignment_a[key]:
                    raise RunnerError(
                        "Reviewer B evidence/interface boundary differs from Reviewer A"
                    )
        return value

    def _validate_path_hash_map(
        self, paths: Sequence[str], hashes: Any, position: int
    ) -> None:
        if not isinstance(hashes, dict) or set(hashes) != set(paths):
            raise RunnerError("assignment path/hash map differs")
        for raw in paths:
            relative = self._safe_relative(raw)
            match = POSITION_SEGMENT_RE.search(f"/{relative}")
            if match and int(match.group(1)) != position:
                raise RunnerError("assignment crosses the current-position boundary")
            path = self.worktree / relative
            if path.is_symlink() or not path.is_file():
                raise RunnerError(f"permitted assignment file is absent: {relative}")
            digest = hashes[raw]
            if not isinstance(digest, str) or sha256_file(path) != digest:
                raise RunnerError(f"assignment hash mismatch: {relative}")

    @staticmethod
    def _safe_relative(raw: Any) -> PurePosixPath:
        if not isinstance(raw, str):
            raise RunnerError("artifact path must be text")
        path = PurePosixPath(raw)
        if (
            path.is_absolute()
            or path.as_posix() != raw
            or "\\" in raw
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise RunnerError(f"artifact path is not canonical and relative: {raw}")
        return path

    def _validate_ai_output(
        self, output_path: Path, packet_path: Path
    ) -> tuple[dict[str, Any], str]:
        value = read_json(output_path)
        required = {
            "review_packet_sha256",
            "candidate_id",
            "focal_hypothesis",
            "answers",
            "outcome",
            "non_authoritative_commentary",
        }
        if not isinstance(value, dict) or set(value) != required:
            raise RunnerError("AI semantic output fields are not exact")
        source_root = str(self.worktree / "src")
        inserted = source_root not in sys.path
        if inserted:
            sys.path.insert(0, source_root)
        try:
            from cmpilot.tptm.codes import (  # type: ignore
                PredicateType,
                TransitionType,
                WitnessType,
            )
            from cmpilot.tptm.review import (  # type: ignore
                FocalHypothesis,
                HumanReviewAction,
                ReviewAnswer,
                ReviewAnswerValue,
                ReviewDecision,
                ReviewOutcome,
                ReviewerRole,
                review_decision_payload,
                seal_review_decision,
                validate_review_packet_bytes,
            )

            packet = validate_review_packet_bytes(packet_path.read_bytes())
            focal = value["focal_hypothesis"]
            if not isinstance(focal, dict):
                raise RunnerError("AI focal hypothesis is invalid")
            decision = ReviewDecision(
                schema_version="tptm-review-decision-v1",
                protocol_id="tptm-hybrid-screening-v1",
                review_decision_sha256=None,
                review_packet_sha256=value["review_packet_sha256"],
                candidate_id=value["candidate_id"],
                reviewer_role=ReviewerRole.CODEX_PROPOSAL,
                human_action=HumanReviewAction.NOT_APPLICABLE,
                changed_question_ids=(),
                focal_hypothesis=FocalHypothesis(
                    hypothesis_id=focal["hypothesis_id"],
                    predicate_type=(
                        None
                        if focal["predicate_type"] is None
                        else PredicateType(focal["predicate_type"])
                    ),
                    transition_type=(
                        None
                        if focal["transition_type"] is None
                        else TransitionType(focal["transition_type"])
                    ),
                    witness_type=(
                        None
                        if focal["witness_type"] is None
                        else WitnessType(focal["witness_type"])
                    ),
                    protected_effect_ref=focal["protected_effect_ref"],
                    evidence_refs=tuple(focal["evidence_refs"]),
                ),
                answers=tuple(
                    ReviewAnswer(
                        question_id=item["question_id"],
                        answer=ReviewAnswerValue(item["answer"]),
                        evidence_refs=tuple(item["evidence_refs"]),
                    )
                    for item in value["answers"]
                ),
                outcome=ReviewOutcome(value["outcome"]),
                non_authoritative_commentary=value["non_authoritative_commentary"],
            )
            sealed = seal_review_decision(decision)
            if (
                packet.review_packet_sha256 != value["review_packet_sha256"]
                or packet.candidate_result.candidate_id != value["candidate_id"]
            ):
                raise RunnerError("AI output and review packet identities differ")
            resolvable = {item.evidence_id for item in packet.evidence_index}
            cited = set(decision.focal_hypothesis.evidence_refs)
            cited.update(
                ref for answer in decision.answers for ref in answer.evidence_refs
            )
            if not cited <= resolvable:
                raise RunnerError("AI output contains unresolved evidence references")
            projection_sha256 = sha256_bytes(
                canonical_review_projection_bytes(review_decision_payload(sealed))
            )
            return value, projection_sha256
        except RunnerError:
            raise
        except Exception as error:
            raise RunnerError(f"invalid AI reviewer decision: {error}") from error
        finally:
            if inserted:
                sys.path.remove(source_root)

    def assignment_bound_evidence_contract(
        self, assignment: Mapping[str, Any]
    ) -> tuple[Any, dict[str, Any], Any]:
        """Build the provider contract from only this assignment and its packet."""

        source_root = str(self.worktree / "src")
        inserted = source_root not in sys.path
        if inserted:
            sys.path.insert(0, source_root)
        try:
            from cmpilot.ai_review_evidence_reference_interface_v01 import (  # type: ignore
                EvidenceReferenceContractError,
                build_assignment_bound_evidence_contract,
            )
            from cmpilot.tptm.review import (  # type: ignore
                validate_review_packet_bytes,
            )

            schema = read_json(
                self.provider_correction_path / AI_PROVIDER_OUTPUT_SCHEMA
            )
            profile = read_json(
                self.provider_correction_path / AI_PROVIDER_COMPATIBILITY_PROFILE
            )
            if not isinstance(schema, dict) or not isinstance(profile, dict):
                raise ProviderEvidenceReferenceContractError(
                    "provider interface artifacts must be objects"
                )
            loaded_packet: list[Any] = []

            def load_packet(raw: str) -> Any:
                packet_path = self.worktree / self._safe_relative(raw)
                packet = validate_review_packet_bytes(packet_path.read_bytes())
                loaded_packet.append(packet)
                return packet

            contract = build_assignment_bound_evidence_contract(
                schema, profile, assignment, load_packet
            )
            if len(loaded_packet) != 1:
                raise ProviderEvidenceReferenceContractError(
                    "assignment-bound review packet load is not singular"
                )
            return contract, profile, loaded_packet[0]
        except ProviderEvidenceReferenceContractError:
            raise
        except EvidenceReferenceContractError as error:
            raise ProviderEvidenceReferenceContractError(str(error)) from error
        except Exception as error:
            raise ProviderEvidenceReferenceContractError(
                f"assignment-bound evidence contract is invalid: {error}"
            ) from error
        finally:
            if inserted:
                sys.path.remove(source_root)

    def _project_provider_output(
        self, output_path: Path, assignment: Mapping[str, Any]
    ) -> tuple[dict[str, Any], str]:
        value = read_json(output_path)
        source_root = str(self.worktree / "src")
        inserted = source_root not in sys.path
        if inserted:
            sys.path.insert(0, source_root)
        try:
            from cmpilot.ai_review_evidence_reference_interface_v01 import (  # type: ignore
                EvidenceReferenceContractError,
                project_assignment_bound_provider_to_canonical,
            )
            from cmpilot.ai_review_provider_interface_v01 import (  # type: ignore
                validate_projection_with_packet,
            )

            contract, profile, packet = self.assignment_bound_evidence_contract(
                assignment
            )
            projection = project_assignment_bound_provider_to_canonical(
                value, contract, profile
            )
            validate_projection_with_packet(projection, packet)
            return (
                projection.semantic_decision,
                projection.semantic_projection_sha256,
            )
        except ProviderEvidenceReferenceContractError:
            raise
        except EvidenceReferenceContractError as error:
            raise ProviderEvidenceReferenceContractError(str(error)) from error
        except RunnerError:
            raise
        except Exception as error:
            raise RunnerError(
                f"invalid provider AI reviewer decision: {error}"
            ) from error
        finally:
            if inserted:
                sys.path.remove(source_root)

    def validate_ai_decision(self, path: Path, role: Role) -> dict[str, Any]:
        value = read_json(path)
        if not isinstance(value, dict):
            raise RunnerError("AI decision must be an object")
        digest = value.get("decision_sha256")
        payload = {key: item for key, item in value.items() if key != "decision_sha256"}
        if not isinstance(digest, str) or digest != sha256_bytes(
            canonical_json_bytes(payload)
        ):
            raise RunnerError("AI decision SHA-256 differs")
        expected_role = (
            "AI_FIRST_REVIEW" if role is Role.AI_FIRST_REVIEW else "AI_SECOND_REVIEW"
        )
        if (
            value.get("schema_version") != AI_DECISION_SCHEMA_VERSION
            or value.get("amendment_id") != AMENDMENT_ID
            or value.get("reviewer_type") != "AI"
            or value.get("reviewer_role") != expected_role
            or value.get("authority") != "AUTHORITATIVE_SEMANTIC_REVIEW"
            or value.get("effective_position") != EFFECTIVE_POSITION
        ):
            raise RunnerError("AI decision authority/provenance differs")
        provenance = value.get("codex_provenance")
        if (
            not isinstance(provenance, dict)
            or provenance.get("fresh_process") is not True
            or provenance.get("resumed_or_forked") is not False
        ):
            raise RunnerError("AI decision fresh-process provenance differs")
        assignment_path = self.worktree / self._safe_relative(value["assignment_path"])
        assignment = self.validate_assignment(assignment_path, role)
        if sha256_file(assignment_path) != value.get("assignment_sha256"):
            raise RunnerError("AI decision assignment SHA-256 differs")
        packet_path = self.worktree / self._safe_relative(
            assignment["review_packet"]["path"]
        )
        semantic_path = self._temporary_semantic_output(value["semantic_decision"])
        try:
            semantic, projection = self._validate_ai_output(semantic_path, packet_path)
        finally:
            semantic_path.unlink(missing_ok=True)
        if semantic != value["semantic_decision"] or projection != value.get(
            "semantic_projection_sha256"
        ):
            raise RunnerError("AI decision semantic projection differs")
        return value

    @staticmethod
    def _frozen_projection_mapping(semantic: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": "tptm-review-decision-v1",
            "protocol_id": "tptm-hybrid-screening-v1",
            "review_decision_sha256": None,
            "review_packet_sha256": semantic["review_packet_sha256"],
            "candidate_id": semantic["candidate_id"],
            "reviewer_role": "CODEX_PROPOSAL",
            "human_action": "NOT_APPLICABLE",
            "changed_question_ids": [],
            "focal_hypothesis": semantic["focal_hypothesis"],
            "answers": semantic["answers"],
            "outcome": semantic["outcome"],
            "non_authoritative_commentary": semantic[
                "non_authoritative_commentary"
            ],
        }

    def reviewer_b_requirement(self, position: int) -> tuple[bool, str, int]:
        decision_path = self.position_path(position) / "ai-reviewer-a-decision.json"
        decision = self.validate_ai_decision(decision_path, Role.AI_FIRST_REVIEW)
        assignment_path = self.position_path(position) / "ai-reviewer-a-assignment.json"
        assignment = self.validate_assignment(assignment_path, Role.AI_FIRST_REVIEW)
        packet_path = self.worktree / self._safe_relative(
            assignment["review_packet"]["path"]
        )
        source_root = str(self.worktree / "src")
        inserted = source_root not in sys.path
        if inserted:
            sys.path.insert(0, source_root)
        try:
            from cmpilot.tptm.review import (  # type: ignore
                review_decision_from_mapping,
                second_review_requirement,
                validate_review_packet_bytes,
            )

            projection = review_decision_from_mapping(
                self._frozen_projection_mapping(decision["semantic_decision"])
            )
            packet = validate_review_packet_bytes(packet_path.read_bytes())
            requirement = second_review_requirement(
                projection, packet.candidate_result
            )
            return (
                requirement.required,
                requirement.reason.value,
                requirement.hash_bucket,
            )
        except Exception as error:
            raise RunnerError(f"cannot calculate frozen Reviewer B trigger: {error}") from error
        finally:
            if inserted:
                sys.path.remove(source_root)

    def _verify_amended_terminal_record(
        self, position: int, record: Mapping[str, Any]
    ) -> None:
        routing = record.get("hybrid_routing_state")
        position_path = self.position_path(position)
        decision_a_path = position_path / "ai-reviewer-a-decision.json"
        decision_b_path = position_path / "ai-reviewer-b-decision.json"
        if routing != "STRUCTURED_REVIEW_REQUIRED":
            if (
                record.get("reviewer_a_decision_sha256") is not None
                or record.get("reviewer_b_decision_sha256") is not None
                or decision_a_path.exists()
                or decision_b_path.exists()
            ):
                raise RunnerError("automatic amended terminal record has reviewer material")
            return
        decision_a = self.validate_ai_decision(
            decision_a_path, Role.AI_FIRST_REVIEW
        )
        if record.get("reviewer_a_decision_sha256") != decision_a[
            "decision_sha256"
        ]:
            raise RunnerError("terminal record AI Reviewer A hash differs")
        reviewer_b_required, _, _ = self.reviewer_b_requirement(position)
        if reviewer_b_required:
            decision_b = self.validate_ai_decision(
                decision_b_path, Role.AI_SECOND_REVIEW
            )
            if record.get("reviewer_b_decision_sha256") != decision_b[
                "decision_sha256"
            ]:
                raise RunnerError("terminal record AI Reviewer B hash differs")
            combined, _ = combine_review_metadata(
                decision_a["semantic_decision"], decision_b["semantic_decision"]
            )
            focal_values = (
                decision_a["semantic_decision"]["focal_hypothesis"],
                decision_b["semantic_decision"]["focal_hypothesis"],
            )
        else:
            if record.get("reviewer_b_decision_sha256") is not None or decision_b_path.exists():
                raise RunnerError("terminal record contains untriggered Reviewer B material")
            combined = decision_a["semantic_decision"]["outcome"]
            focal_values = (decision_a["semantic_decision"]["focal_hypothesis"],)
        if record.get("combined_review_state") != combined:
            raise RunnerError("terminal record combined review state differs")
        no_unique_focal = any(
            focal.get("predicate_type") is None
            or focal.get("transition_type") is None
            or focal.get("witness_type") is None
            or focal.get("protected_effect_ref") is None
            for focal in focal_values
        ) or (len(focal_values) == 2 and focal_values[0] != focal_values[1])
        if (
            combined == "REVIEW_UNRESOLVED"
            and no_unique_focal
            and record.get("processing_state") != "FAMILY_CONSTRUCTION_FAILED"
        ):
            raise RunnerError(
                "no-unique-focal review did not use frozen family failure"
            )

    def _temporary_semantic_output(self, value: Any) -> Path:
        descriptor, name = tempfile.mkstemp(prefix="track-a-ai-decision-", suffix=".json")
        path = Path(name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical_json_bytes(value))
        return path

    def last_terminal_processing_state(self, position: int) -> str:
        record = read_json(self.run_path / "records" / f"{position:08d}.json")
        state = record.get("processing_state")
        if not isinstance(state, str):
            raise RunnerError("terminal record processing state is invalid")
        return state


def PHASE_FOR_ROLE(role: Role) -> Phase:
    return {
        Role.POSITION_CONTROLLER: Phase.NEED_CONTROLLER,
        Role.AI_FIRST_REVIEW: Phase.NEED_REVIEW_A,
        Role.CONTINUATION_CONTROLLER: Phase.NEED_CONTINUATION,
        Role.AI_SECOND_REVIEW: Phase.NEED_REVIEW_B,
        Role.COMBINATION_CONTINUATION_CONTROLLER: Phase.NEED_COMBINATION,
    }[role]


class CodexRoleExecutor:
    def __init__(
        self,
        repository: ProductionRepository,
        logger: AppendOnlyLogger,
        codex_bin: Path,
        model: str | None,
        profile: str | None,
    ) -> None:
        self.repository = repository
        self.logger = logger
        self.codex_bin = codex_bin.resolve()
        self.model = model
        self.profile = profile
        self.attempts: dict[tuple[int, Role], int] = {}
        prompts = read_json(
            repository.amendment_path / "role-prompts.json"
        )
        if not isinstance(prompts, dict):
            raise RunnerError("role prompt artifact must be an object")
        self.prompts = prompts

    def execute(
        self, role: Role, position: int, expected_head: str
    ) -> RoleExecution:
        key = (position, role)
        attempt = self.attempts.get(key, 0) + 1
        self.attempts[key] = attempt
        role_dir = self.logger.role_attempt_dir(position, role, attempt)
        assignment: dict[str, Any] | None = None
        if role is Role.AI_FIRST_REVIEW:
            assignment_path = (
                self.repository.position_path(position) / "ai-reviewer-a-assignment.json"
            )
            assignment = self.repository.validate_assignment(assignment_path, role)
        elif role is Role.AI_SECOND_REVIEW:
            assignment_path = self.repository.latest_b_assignment(position)
            if assignment_path is None:
                raise RunnerError("Reviewer B assignment is absent")
            assignment = self.repository.validate_assignment(assignment_path, role)
        else:
            assignment_path = None
        prompt = self.render_prompt(
            role,
            position,
            expected_head,
            assignment_path=assignment_path,
            assignment=assignment,
        )
        prompt_digest = sha256_bytes(prompt.encode("utf-8"))
        write_exclusive(role_dir / "prompt.txt", prompt.encode("utf-8"), mode=0o600)
        write_exclusive(
            role_dir / "prompt.sha256",
            f"{prompt_digest}  prompt.txt\n".encode("ascii"),
            mode=0o600,
        )
        ledger_before = self.repository.ledger_path.read_bytes()
        write_exclusive(role_dir / "ledger-before.json", ledger_before, mode=0o600)
        invocation_id = str(uuid.uuid4())
        started = utc_now()
        if role in {Role.AI_FIRST_REVIEW, Role.AI_SECOND_REVIEW}:
            execution = self._execute_isolated_reviewer(
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
        else:
            execution = self._execute_controller(
                role,
                position,
                prompt,
                prompt_digest,
                invocation_id,
                started,
                role_dir,
            )
        ledger_after = (
            self.repository.ledger_path.read_bytes()
            if self.repository.ledger_path.is_file()
            else b"ABSENT\n"
        )
        write_exclusive(role_dir / "ledger-after.json", ledger_after, mode=0o600)
        metadata = {
            "schema": "track-a-codex-role-log-v0.1",
            "runner_id": self.logger.runner_id,
            "position": position,
            "role": role.value,
            "invocation_id": invocation_id,
            "expected_head": expected_head,
            "actual_starting_head": self.repository.state["expected_head"],
            "ending_head": self.repository._git("rev-parse", "HEAD").strip(),
            "start_timestamp": started,
            "end_timestamp": execution.ended_at_utc,
            "codex_process_session_id": execution.codex_thread_id,
            "codex_cli_version": self.repository._amendment()["external_runner"][
                "codex_cli_version"
            ],
            "model_identifier": execution.model_identifier,
            "profile_identifier": self.profile,
            "prompt_sha256": prompt_digest,
            "assignment_sha256": (
                sha256_file(assignment_path) if assignment_path is not None else None
            ),
            "packet_sha256": (
                assignment["review_packet"]["review_packet_sha256"]
                if assignment is not None
                else None
            ),
            "codex_exit_code": execution.exit_code,
            "infrastructure_failure": execution.infrastructure_failure,
            "partial_decision_present": execution.partial_decision_present,
            "orchestration_classification": ROLE_CLASSIFICATION[role].value,
            "fresh_process": True,
            "resume_or_fork_used": False,
        }
        write_exclusive(
            role_dir / "metadata.json",
            json.dumps(metadata, ensure_ascii=False, indent=2).encode("utf-8") + b"\n",
            mode=0o600,
        )
        return execution

    def render_prompt(
        self,
        role: Role,
        position: int,
        expected_head: str,
        *,
        assignment_path: Path | None = None,
        assignment: Mapping[str, Any] | None = None,
    ) -> str:
        keys = {
            Role.POSITION_CONTROLLER: "position_controller",
            Role.AI_FIRST_REVIEW: "ai_first_review",
            Role.CONTINUATION_CONTROLLER: "continuation_controller",
            Role.AI_SECOND_REVIEW: "ai_second_review",
            Role.COMBINATION_CONTINUATION_CONTROLLER: "combination_continuation_controller",
        }
        lines = self.prompts.get(keys[role])
        if not isinstance(lines, list) or any(not isinstance(line, str) for line in lines):
            raise RunnerError(f"frozen prompt template is invalid for {role.value}")
        values = {
            "POSITION": str(position),
            "POSITION_PADDED": f"{position:08d}",
            "NEXT_POSITION": str(position + 1),
            "EXPECTED_HEAD": expected_head,
            "WORKTREE": str(self.repository.worktree),
            "RUN_PATH": str(RUN_RELATIVE_PATH),
            "AMENDMENT_PATH": str(AMENDMENT_RELATIVE_PATH),
            "ASSIGNMENT_FILE": (
                "assignment.json" if assignment_path is not None else "NOT_APPLICABLE"
            ),
            "ASSIGNMENT_SHA256": (
                sha256_file(assignment_path) if assignment_path is not None else "NOT_APPLICABLE"
            ),
            "PACKET_SHA256": (
                str(assignment["review_packet"]["review_packet_sha256"])
                if assignment is not None
                else "NOT_APPLICABLE"
            ),
        }
        prompt = "\n".join(lines) + "\n"
        for name, value in values.items():
            prompt = prompt.replace("{{" + name + "}}", value)
        if "{{" in prompt or "}}" in prompt:
            raise RunnerError(f"unresolved frozen prompt placeholder for {role.value}")
        if role in {Role.AI_FIRST_REVIEW, Role.AI_SECOND_REVIEW}:
            if assignment is None:
                raise ProviderEvidenceReferenceContractError(
                    "AI reviewer prompt assignment is absent"
                )
            contract, _, _ = self.repository.assignment_bound_evidence_contract(
                assignment
            )
            source_root = str(self.repository.worktree / "src")
            inserted = source_root not in sys.path
            if inserted:
                sys.path.insert(0, source_root)
            try:
                from cmpilot.ai_review_evidence_reference_interface_v01 import (  # type: ignore
                    evidence_reference_prompt,
                )

                prompt += evidence_reference_prompt(contract) + "\n"
            finally:
                if inserted:
                    sys.path.remove(source_root)
        return prompt

    def _base_codex_arguments(self) -> list[str]:
        command = [
            "exec",
            "--json",
            "--ephemeral",
            "--ignore-user-config",
            "--color",
            "never",
            UNATTENDED_CODEX_OPTION,
        ]
        if self.model:
            command.extend(["--model", self.model])
        if self.profile:
            command.extend(["--profile", self.profile])
        return command

    def _base_codex_command(self) -> list[str]:
        return [str(self.codex_bin), *self._base_codex_arguments()]

    def _controller_command(self) -> list[str]:
        return [
            *self._base_codex_command(),
            "--cd",
            str(self.repository.worktree),
            "-",
        ]

    def _execute_controller(
        self,
        role: Role,
        position: int,
        prompt: str,
        prompt_digest: str,
        invocation_id: str,
        started: str,
        role_dir: Path,
    ) -> RoleExecution:
        return self._run_process(
            self._controller_command(),
            cwd=self.repository.worktree,
            role=role,
            position=position,
            prompt=prompt,
            prompt_digest=prompt_digest,
            invocation_id=invocation_id,
            started=started,
            role_dir=role_dir,
            last_message_path=None,
        )

    def _execute_isolated_reviewer(
        self,
        role: Role,
        position: int,
        prompt: str,
        prompt_digest: str,
        invocation_id: str,
        started: str,
        role_dir: Path,
        assignment_path: Path | None,
        assignment: Mapping[str, Any] | None,
    ) -> RoleExecution:
        if assignment_path is None or assignment is None:
            raise RunnerError("isolated reviewer assignment is absent")
        self.verify_reviewer_output_schema(role, assignment)
        contract, _, _ = self.repository.assignment_bound_evidence_contract(
            assignment
        )
        with tempfile.TemporaryDirectory(
            prefix=f"track-a-position-{position:08d}-review-",
            dir=self.repository.runner_root,
        ) as temporary:
            capsule = Path(temporary) / "capsule"
            capsule.mkdir()
            shutil.copyfile(assignment_path, capsule / "assignment.json")
            copied: list[dict[str, str]] = []
            permitted = [
                *assignment["permitted_evidence_paths"],
                *assignment["permitted_interface_paths"],
            ]
            for raw in permitted:
                relative = self.repository._safe_relative(raw)
                source = self.repository.worktree / relative
                destination = capsule / "repository" / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
                copied.append({"path": raw, "sha256": sha256_file(destination)})
            write_exclusive(
                capsule / AI_OUTPUT_SCHEMA,
                canonical_json_bytes(contract.provider_schema),
                mode=0o444,
            )
            write_exclusive(
                capsule / "capsule-manifest.json",
                canonical_json_bytes(
                    {
                        "schema": "track-a-review-capsule-v0.1",
                        "position": position,
                        "reviewer_role": role.value,
                        "assignment_sha256": sha256_file(assignment_path),
                        "files": copied,
                    }
                ),
                mode=0o444,
            )
            process_output = role_dir / "process-output"
            process_output.mkdir()
            last_message = process_output / "last-message.json"
            codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
            auth = codex_home / "auth.json"
            if auth.is_symlink() or not auth.is_file():
                raise RunnerError("Codex authentication file unavailable for isolated review")
            codex_install = Path("/home/anjum/.local/npm")
            if codex_install.is_symlink() or not codex_install.is_dir():
                raise RunnerError("Codex installation tree is unavailable")
            try:
                resolver_policy = resolve_resolver_mount_policy()
            except ReviewSandboxConfigurationError as error:
                raise RunnerError(
                    f"reviewer sandbox resolver configuration rejected: {error}"
                ) from error
            command = reviewer_bwrap_prefix(
                capsule=capsule,
                process_output=process_output,
                codex_install=codex_install,
                auth=auth,
                resolver_policy=resolver_policy,
            )
            command.extend(
                [
                    str(self.codex_bin),
                    *self._base_codex_arguments(),
                ]
            )
            command.extend(
                [
                    "--skip-git-repo-check",
                    "--cd",
                    "/workspace",
                    "--output-schema",
                    f"/workspace/{AI_OUTPUT_SCHEMA}",
                    "--output-last-message",
                    "/output/last-message.json",
                    "-",
                ]
            )
            return self._run_process(
                command,
                cwd=self.repository.runner_root,
                role=role,
                position=position,
                prompt=prompt,
                prompt_digest=prompt_digest,
                invocation_id=invocation_id,
                started=started,
                role_dir=role_dir,
                last_message_path=last_message,
            )

    def verify_reviewer_output_schema(
        self,
        role: Role,
        assignment: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if role not in {Role.AI_FIRST_REVIEW, Role.AI_SECOND_REVIEW}:
            raise RunnerError("provider output schema is only defined for AI reviewers")
        source_root = str(self.repository.worktree / "src")
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

            schema_path = (
                self.repository.provider_correction_path / AI_PROVIDER_OUTPUT_SCHEMA
            )
            profile_path = (
                self.repository.provider_correction_path
                / AI_PROVIDER_COMPATIBILITY_PROFILE
            )
            for path in (schema_path, profile_path):
                if path.is_symlink() or not path.is_file():
                    raise RunnerError(f"provider interface artifact is absent: {path}")
            schema = read_json(schema_path)
            profile = read_json(profile_path)
            if not isinstance(schema, dict) or not isinstance(profile, dict):
                raise RunnerError("provider interface artifacts must be objects")
            validate_provider_schema_compatibility(schema, profile)
            if assignment is None:
                contract_schema = bind_provider_schema_to_allowed_refs(
                    schema, profile, ("synthetic-evidence-reference",)
                )
                contract_role = role.value
                allowed_count = 1
            else:
                contract, _, _ = self.repository.assignment_bound_evidence_contract(
                    assignment
                )
                if contract.reviewer_role != role.value:
                    raise ProviderEvidenceReferenceContractError(
                        "provider contract reviewer role differs"
                    )
                contract_schema = contract.provider_schema
                contract_role = contract.reviewer_role
                allowed_count = len(contract.allowed_evidence_refs)
            contract_schema_sha256 = sha256_bytes(
                canonical_json_bytes(contract_schema)
            )
            if assignment is not None and (
                contract_schema_sha256 != contract.provider_schema_sha256
            ):
                raise ProviderEvidenceReferenceContractError(
                    "provider contract schema byte identity differs"
                )
            return {
                "role": contract_role,
                "schema_path": str(schema_path),
                "schema_sha256": contract_schema_sha256,
                "template_schema_sha256": sha256_file(schema_path),
                "profile_path": str(profile_path),
                "profile_sha256": sha256_file(profile_path),
                "capsule_schema_path": f"/workspace/{AI_OUTPUT_SCHEMA}",
                "allowed_evidence_ref_count": allowed_count,
            }
        except RunnerError:
            raise
        except Exception as error:
            raise RunnerError(
                f"provider output schema is incompatible: {error}"
            ) from error
        finally:
            if inserted:
                sys.path.remove(source_root)

    def _run_process(
        self,
        command: Sequence[str],
        *,
        cwd: Path,
        role: Role,
        position: int,
        prompt: str,
        prompt_digest: str,
        invocation_id: str,
        started: str,
        role_dir: Path,
        last_message_path: Path | None,
    ) -> RoleExecution:
        if "resume" in command or "fork" in command:
            raise RunnerError("resume/fork is prohibited across logical roles")
        process = subprocess.run(
            list(command),
            cwd=cwd,
            input=prompt,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            env=sanitized_environment(),
        )
        ended = utc_now()
        write_exclusive(role_dir / "stdout.jsonl", process.stdout.encode("utf-8"))
        write_exclusive(role_dir / "stderr.txt", process.stderr.encode("utf-8"))
        thread_id, observed_model = parse_codex_jsonl(process.stdout)
        return RoleExecution(
            role=role,
            position=position,
            invocation_id=invocation_id,
            started_at_utc=started,
            ended_at_utc=ended,
            exit_code=process.returncode,
            stdout=process.stdout,
            stderr=process.stderr,
            prompt=prompt,
            prompt_sha256=prompt_digest,
            codex_thread_id=thread_id,
            model_identifier=observed_model or self.model or "CLI_DEFAULT_SELECTOR",
            profile_identifier=self.profile,
            last_message_path=last_message_path,
        )


def parse_codex_jsonl(output: str) -> tuple[str | None, str | None]:
    thread_id = None
    model = None
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "thread.started":
            candidate = event.get("thread_id") or event.get("thread", {}).get("id")
            if isinstance(candidate, str):
                thread_id = candidate
        candidate_model = event.get("model")
        if isinstance(candidate_model, str):
            model = candidate_model
    return thread_id, model


def combine_review_metadata(
    first: Mapping[str, Any], second: Mapping[str, Any]
) -> tuple[str, str]:
    """Mechanically mirror the frozen exact-disagreement rule.

    This helper consumes only already-authoritative decision metadata.  It is
    used for validation/tests; semantic combination remains a fresh controller
    role in production.
    """

    required = {"candidate_id", "review_packet_sha256", "answers", "outcome", "focal_hypothesis"}
    if not required <= set(first) or not required <= set(second):
        raise RunnerError("review combination metadata is incomplete")
    if (
        first["candidate_id"] != second["candidate_id"]
        or first["review_packet_sha256"] != second["review_packet_sha256"]
    ):
        raise RunnerError("review decisions do not concern the same packet")
    if (
        first["answers"] != second["answers"]
        or first["outcome"] != second["outcome"]
        or first["focal_hypothesis"] != second["focal_hypothesis"]
    ):
        return (
            "REVIEW_UNRESOLVED",
            "CONSTRAINED_FAMILY_FEASIBILITY_INVESTIGATION",
        )
    return str(first["outcome"]), "AGREEMENT"


def render_dry_run(
    repository: ProductionRepository,
    executor: CodexRoleExecutor,
    snapshot: Snapshot,
    max_positions: int,
) -> str:
    phase = repository.phase(snapshot.next_due_position)
    if phase is not Phase.NEED_CONTROLLER:
        raise RunnerError("dry run requires an unopened due position")
    prompt = executor.render_prompt(
        Role.POSITION_CONTROLLER,
        snapshot.next_due_position,
        snapshot.head,
    )
    prompt_digest = sha256_bytes(prompt.encode("utf-8"))
    sequence = {
        "position": snapshot.next_due_position,
        "branches": [
            ["POSITION_CONTROLLER", "TERMINAL", "AUTO_CONTINUE"],
            [
                "POSITION_CONTROLLER",
                "AI_FIRST_REVIEW",
                "CONTINUATION_CONTROLLER",
                "TERMINAL_IF_REVIEWER_B_NOT_REQUIRED",
            ],
            [
                "POSITION_CONTROLLER",
                "AI_FIRST_REVIEW",
                "CONTINUATION_CONTROLLER",
                "AI_SECOND_REVIEW",
                "COMBINATION_CONTINUATION_CONTROLLER",
                "TERMINAL",
            ],
        ],
        "fresh_codex_process_per_role": True,
        "resume_or_fork": False,
        "next_position_before_terminal": False,
    }
    sequence_digest = sha256_bytes(canonical_json_bytes(sequence))
    prompt_artifact = read_json(repository.amendment_path / "role-prompts.json")
    template_hashes = {
        name: sha256_bytes(("\n".join(lines) + "\n").encode("utf-8"))
        for name, lines in prompt_artifact.items()
        if name not in {"schema", "amendment_id"} and isinstance(lines, list)
    }
    lines = [
        "classification=DRY_RUN",
        f"branch={EXPECTED_BRANCH}",
        f"head={snapshot.head}",
        f"records_published={snapshot.records_published}",
        f"successor_positions_processed={snapshot.successor_positions_processed}",
        f"historical_unique_opened_anchors={snapshot.historical_unique_opened_anchors}",
        f"global_unique_opened_anchors={snapshot.global_unique_opened_anchors}",
        f"FINAL={snapshot.final}",
        f"categories_represented={snapshot.categories_represented}",
        f"next_due_position={snapshot.next_due_position}",
        f"global_action={snapshot.global_action}",
        f"max_positions={max_positions}",
        f"model_selector={executor.model}",
        f"profile_selector={executor.profile}",
        f"effective_runner_correction_id={CORRECTION_ID}",
        "position_controller_invocation="
        + json.dumps(executor._controller_command()),
        f"state_sequence_sha256={sequence_digest}",
        "state_sequence=" + json.dumps(sequence, sort_keys=True),
        "role_template_hashes=" + json.dumps(template_hashes, sort_keys=True),
        f"position_controller_prompt_sha256={prompt_digest}",
        "BEGIN_EXACT_POSITION_CONTROLLER_PROMPT",
        prompt.rstrip("\n"),
        "END_EXACT_POSITION_CONTROLLER_PROMPT",
        "codex_role_invocations=0",
        "position_authorization_created=false",
        "candidate_content_inspected=false",
        "ledger_modified=false",
        "repository_modified=false",
    ]
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="External fail-closed Track A autonomous production runner"
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-positions", type=int, default=DEFAULT_MAX_POSITIONS)
    parser.add_argument("--worktree", type=Path, default=DEFAULT_WORKTREE)
    parser.add_argument(
        "--runner-root",
        type=Path,
        default=Path(os.environ.get("TRACK_A_RUNNER_ROOT", DEFAULT_RUNNER_ROOT)),
    )
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--codex-bin", type=Path)
    parser.add_argument("--model", default=DEFAULT_CODEX_MODEL)
    parser.add_argument("--profile")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.max_positions <= 0:
        print("ERROR: --max-positions must be positive", file=sys.stderr)
        return 2
    runner_root = args.runner_root.resolve()
    runner_root.mkdir(parents=True, exist_ok=True)
    runner_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:12]
    logger: AppendOnlyLogger | None = None
    try:
        logger = AppendOnlyLogger(runner_root, runner_id)
        state_path = args.state_file or runner_root / "state" / "runner-state.json"
        repository = ProductionRepository(
            args.worktree, runner_root, state_path, logger
        )
        codex_bin = args.codex_bin
        if codex_bin is None:
            found = shutil.which("codex")
            codex_bin = Path(found) if found else None
        snapshot = repository.preflight(dry_run=args.dry_run, codex_bin=codex_bin)
        frozen_runner = repository._amendment()["external_runner"]
        if args.model != frozen_runner["model_selector"]:
            raise RunnerError("model selector differs from the frozen runner profile")
        if args.profile != frozen_runner["profile_selector"]:
            raise RunnerError("profile selector differs from the frozen runner profile")
        executor = CodexRoleExecutor(
            repository,
            logger,
            codex_bin or Path("/nonexistent/codex"),
            args.model,
            args.profile,
        )
        if args.dry_run:
            before = repository.durable_token(snapshot.next_due_position)
            report = render_dry_run(
                repository, executor, snapshot, args.max_positions
            )
            after = repository.durable_token(snapshot.next_due_position)
            if before != after:
                raise RunnerError("dry run changed durable production state")
            logger.emit(
                Classification.DRY_RUN,
                next_due_position=snapshot.next_due_position,
                prompt_sha256=sha256_bytes(
                    executor.render_prompt(
                        Role.POSITION_CONTROLLER,
                        snapshot.next_due_position,
                        snapshot.head,
                    ).encode("utf-8")
                ),
            )
            sys.stdout.write(report)
            return 0
        state_machine = StateMachine(repository, executor, logger)
        outcome = state_machine.run(args.max_positions)
        print(
            json.dumps(
                {
                    "classification": outcome.classification.value,
                    "positions_completed": outcome.positions_completed,
                    "next_due_position": outcome.next_due_position,
                    "message": outcome.message,
                    "runner_id": runner_id,
                },
                sort_keys=True,
            )
        )
        return 0 if outcome.classification in {
            Classification.GLOBAL_STOP,
            Classification.MAX_POSITION_STOP,
        } else 1
    except RunnerError as error:
        if logger is not None:
            logger.emit(Classification.ERROR, reason=str(error))
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        reason = f"UNEXPECTED_FAIL_CLOSED_ERROR: {type(error).__name__}: {error}"
        if logger is not None:
            logger.emit(Classification.ERROR, reason=reason)
        print(f"ERROR: {reason}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
