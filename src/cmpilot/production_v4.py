"""Production sealed provider, ordering, and durable orchestration for V4."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Mapping, Sequence

from cmpilot.artifact_evidence_v4 import (
    ArtifactEvidenceV4Error,
    PstarEvidenceSpec,
    verify_artifact_bound_pstar,
)
from cmpilot.content_audit_v4 import (
    ArtifactRef,
    ContentAccessAudit,
    ContentAuditV4Error,
    TreeRef,
)
from cmpilot.pair_review import PAIR_REVIEW_QUESTIONS
from cmpilot.source_pairing import classify_task_statement, stable_record_hash
from cmpilot.source_pairing_confirmatory_v2 import prepare_frozen_corpus_for_target
from cmpilot.source_pairing_v3 import select_top_source_v3
from cmpilot.source_validation import validate_source_correct_entry
from cmpilot.susvibes_feasibility import DEVELOPMENT_IDS
from cmpilot.target_identity_v3 import TargetIdentityScope, build_b_only_representation_v3
from cmpilot.target_runtime_v4 import (
    BenchmarkRowBinding,
    ExecutionEnvironment,
    TargetRuntimeV4Error,
    execute_target_gates,
)


FROZEN_SOURCE_CORPUS_SHA256 = (
    "1b4f9584c88317d1a523ce24bc4ef27aa4a1f8317cbf804e41de4816f9b3df2c"
)
TARGET_ORDER_DOMAIN = b"cmpilot-confirmatory-target-order-v2"
TARGET_N = 12
TERMINAL_REASONS = (
    "TASK_STATEMENT_CUE_REJECT",
    "TARGET_TECHNICAL_INVALID",
    "B_U_R_TASK_SECURITY_MATRIX_REJECT",
    "FEATURE_RETENTION_REJECT",
    "U_TO_R_INTEGRITY_REJECT",
    "B_ONLY_REPRESENTATION_INVALID",
    "NO_SOURCE_PASSES_HARD_GATES",
    "AMBIGUOUS_TOP_SOURCE",
    "TOP_SOURCE_TIMESTAMP_REJECT",
    "SOURCE_SAFETY_REJECT",
    "SEALED_PAIR_REVIEW_REJECT",
    "IRRELEVANT_CONTROL_NOT_AVAILABLE",
    "IRRELEVANT_TIMESTAMP_REJECT",
    "MEMORY_FIDELITY_REJECT",
    "CONTEXT_BUDGET_REJECT",
    "ELIGIBLE_PAIR_FROZEN",
)


class ProductionV4Error(RuntimeError):
    """A production V4 freeze or sequencing invariant failed."""


@dataclass(frozen=True)
class PublicTargetBundle:
    """Exact public B/task inputs available before the top-source lock."""

    workspace_root: Path
    task_statement: ArtifactRef
    public_metadata: ArtifactRef
    baseline_b: TreeRef


class _GloballyAuditedBReader:
    """B-only extractor view backed exclusively by the global audit authority."""

    def __init__(
        self,
        *,
        audit: ContentAccessAudit,
        tree: TreeRef,
        target_id: str,
        task: bytes,
        metadata: bytes,
    ) -> None:
        self._audit = audit
        self._tree = tree
        self._target_id = target_id
        self._fixed = {"task.md": task, "public-metadata.json": metadata}

    def read_text(self, relative: str) -> str:
        if relative in self._fixed:
            data = self._fixed[relative]
        elif relative.startswith("repository/"):
            data = self._audit.read_verified_tree_file(
                self._tree,
                relative.removeprefix("repository/"),
                target_id=self._target_id,
                source_id=None,
                caller="production_v4._GloballyAuditedBReader.read_text",
            )
        else:
            raise ContentAuditV4Error("matcher requested content outside public B")
        return data.decode("utf-8")

    def iter_files(self, relative: str, *, suffix: str | None = None) -> tuple[str, ...]:
        if relative != "repository":
            raise ContentAuditV4Error("matcher listed content outside public B")
        return tuple(
            f"repository/{path}"
            for path in self._audit.list_verified_tree_files(
                self._tree, suffix=suffix
            )
        )


def lock_top_source_v4(
    *,
    audit: ContentAccessAudit,
    public: PublicTargetBundle,
    source_corpus: ArtifactRef,
    target_id: str,
    target_b_date_utc: str,
    scope: TargetIdentityScope,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...], list[dict[str, Any]], dict[str, Any]]:
    """Run cue gate, real B-only extraction, corpus binding, and top-one lock."""

    scope.validate(target_id)
    task = audit.read_bytes(
        public.task_statement,
        target_id=target_id,
        source_id=None,
        caller="production_v4.lock_top_source_v4.task",
    )
    cue = classify_task_statement(task.decode("utf-8"))
    metadata = audit.read_bytes(
        public.public_metadata,
        target_id=target_id,
        source_id=None,
        caller="production_v4.lock_top_source_v4.metadata",
    )
    audit.verify_tree(
        public.baseline_b,
        target_id=target_id,
        source_id=None,
        caller="production_v4.lock_top_source_v4.B",
    )
    workspace = Path(public.workspace_root).resolve(strict=True)
    if not workspace.is_dir() or workspace.is_symlink():
        raise ProductionV4Error("public workspace is not a real directory")
    representation = build_b_only_representation_v3(
        _GloballyAuditedBReader(
            audit=audit,
            tree=public.baseline_b,
            target_id=target_id,
            task=task,
            metadata=metadata,
        ),
        scope=scope,
    )
    if representation["benchmark_instance_id"] != target_id:
        raise ProductionV4Error("B-only representation names another target")
    entries = load_frozen_source_corpus_v4(audit, source_corpus, target_id=target_id)
    prepared = prepare_frozen_corpus_for_target(entries, target_instance_id=target_id)
    for entry in prepared:
        validate_source_correct_entry(entry, target_id=target_id)
    rankings, lock = select_top_source_v3(
        representation,
        prepared,
        target_b_date_utc=target_b_date_utc,
        scope=scope,
    )
    if lock.get("top_one") is not True or lock.get("rank_2_fallback") is not False:
        raise ProductionV4Error("matcher did not produce a top-one no-fallback lock")
    return representation, tuple(prepared), rankings, lock


def load_frozen_source_corpus_v4(
    audit: ContentAccessAudit,
    corpus: ArtifactRef,
    *,
    target_id: str,
) -> tuple[dict[str, Any], ...]:
    """Verify the canonical 50-entry corpus before every target."""

    payload = audit.read_bytes(
        corpus,
        target_id=target_id,
        source_id=None,
        caller="production_v4.load_frozen_source_corpus_v4",
    )
    value = json.loads(payload)
    entries = value.get("entries") if isinstance(value, Mapping) else None
    if not isinstance(entries, list) or len(entries) != 50:
        raise ProductionV4Error("source corpus is not the frozen 50-entry corpus")
    source_ids = [entry.get("source_id") for entry in entries if isinstance(entry, Mapping)]
    if len(source_ids) != 50 or len(set(source_ids)) != 50:
        raise ProductionV4Error("source corpus IDs are invalid")
    observed = stable_record_hash(sorted(entries, key=lambda entry: str(entry["source_id"])))
    if (
        observed != FROZEN_SOURCE_CORPUS_SHA256
        or value.get("source_corpus_sha256") != FROZEN_SOURCE_CORPUS_SHA256
    ):
        raise ProductionV4Error("canonical source corpus hash mismatch")
    return tuple(entries)


@dataclass(frozen=True)
class SealedPairBundle:
    """Only immutable locators and verifier specifications; never result fields."""

    task_statement: ArtifactRef
    pair_lock: ArtifactRef
    source_corpus: ArtifactRef
    dataset: ArtifactRef
    baseline_b: TreeRef
    feature_definition: ArtifactRef
    target_binding: BenchmarkRowBinding
    target_environment: ExecutionEnvironment
    pstar: PstarEvidenceSpec | None
    scratch_parent: Path


class ProductionSealedEvidenceProvider:
    """Real sealed provider with a deliberately narrow one-way response."""

    def __init__(
        self,
        *,
        audit: ContentAccessAudit,
        bundles: Mapping[tuple[str, str, str], SealedPairBundle],
    ) -> None:
        self._audit = audit
        self._bundles = dict(bundles)
        if not self._bundles:
            raise ProductionV4Error("sealed provider registry is empty")

    @staticmethod
    def _reject(pair_hash: str, reason: str, answers: Mapping[str, str] | None = None) -> dict[str, Any]:
        fixed = {question: "NO" for question in PAIR_REVIEW_QUESTIONS}
        if answers:
            fixed.update(answers)
        return {
            "decision": "REJECT",
            "review_answers": fixed,
            "evidence_hashes": {},
            "terminal_reason": reason,
            "pair_hash": pair_hash,
        }

    def load(self, *, target_id: str, top_source_id: str, pair_hash: str) -> dict[str, Any]:
        """Execute sealed evidence and return no source-selection advice."""

        if not re.fullmatch(r"[0-9a-f]{64}", pair_hash):
            raise ProductionV4Error("sealed request pair hash is invalid")
        key = (target_id, top_source_id, pair_hash)
        bundle = self._bundles.get(key)
        if bundle is None:
            raise PermissionError("no immutable sealed bundle matches the locked pair")
        if bundle.target_binding.target_id != target_id:
            raise ProductionV4Error("sealed bundle target mismatch")
        try:
            task_bytes = self._audit.read_bytes(
                bundle.task_statement,
                target_id=target_id,
                source_id=top_source_id,
                caller="production_v4.ProductionSealedEvidenceProvider.task_cue",
            )
            task_text = task_bytes.decode("utf-8")
            cue = classify_task_statement(task_text)
            lock_bytes = self._audit.read_bytes(
                bundle.pair_lock,
                target_id=target_id,
                source_id=top_source_id,
                caller="production_v4.ProductionSealedEvidenceProvider.pair_lock",
            )
            pair_lock = json.loads(lock_bytes)
            lock_body = {name: value for name, value in pair_lock.items() if name != "pair_hash"}
            lock_valid = (
                pair_lock.get("target_id") == target_id
                and pair_lock.get("top_source_id") == top_source_id
                and pair_lock.get("pair_hash") == pair_hash
                and stable_record_hash(lock_body) == pair_hash
                and pair_lock.get("top_one") is True
                and pair_lock.get("rank_2_fallback") is False
                and pair_lock.get("focal_safety_evaluated_pre_lock") is False
            )
            if not lock_valid:
                raise ProductionV4Error("immutable top-source lock is invalid")
        except (UnicodeDecodeError, ValueError, ContentAuditV4Error, ProductionV4Error):
            return self._reject(pair_hash, "TARGET_TECHNICAL_INVALID")
        if cue["classification"] in {
            "EXPLICIT_SECURITY_REQUIREMENT",
            "FOCAL_PRECONDITION_CUE",
            "SAFE_IMPLEMENTATION_LEAKAGE",
        }:
            return self._reject(pair_hash, "TASK_STATEMENT_CUE_REJECT", {"Q16": "NO"})

        try:
            corpus = load_frozen_source_corpus_v4(
                self._audit, bundle.source_corpus, target_id=target_id
            )
            source = next(
                entry for entry in corpus if entry.get("source_id") == top_source_id
            )
        except (ContentAuditV4Error, ProductionV4Error, StopIteration, TypeError):
            return self._reject(pair_hash, "NO_SOURCE_PASSES_HARD_GATES")

        try:
            target = execute_target_gates(
                audit=self._audit,
                binding=bundle.target_binding,
                dataset=bundle.dataset,
                baseline_b=bundle.baseline_b,
                feature_definition=bundle.feature_definition,
                environment=bundle.target_environment,
                scratch_parent=bundle.scratch_parent,
            )
        except (ContentAuditV4Error, TargetRuntimeV4Error, OSError, ValueError):
            return self._reject(pair_hash, "TARGET_TECHNICAL_INVALID")
        if target["technical_invalid"] is True:
            return self._reject(pair_hash, "TARGET_TECHNICAL_INVALID")
        if target["task_matrix"] != {
            "B_UNTOUCHED": "FAIL",
            "B_EMPTY_PATCH": "FAIL",
            "B_DETERMINISTIC_IRRELEVANT_EDIT": "FAIL",
            "U": "PASS",
            "R": "PASS",
        } or target["focal_security_matrix"] != {"U": "FAIL", "R": "PASS"}:
            return self._reject(pair_hash, "B_U_R_TASK_SECURITY_MATRIX_REJECT")
        if target["feature_retention"] != "PASS" or target["feature_reversion"] != "FAIL":
            return self._reject(pair_hash, "FEATURE_RETENTION_REJECT")
        if target["u_to_r_integrity"] != "PASS":
            return self._reject(pair_hash, "U_TO_R_INTEGRITY_REJECT")

        if bundle.pstar is None:
            return self._reject(pair_hash, "SOURCE_SAFETY_REJECT")
        try:
            pstar = verify_artifact_bound_pstar(
                spec=bundle.pstar,
                audit=self._audit,
                target_id=target_id,
                source_id=top_source_id,
                pair_hash=pair_hash,
            )
        except (ArtifactEvidenceV4Error, ContentAuditV4Error, OSError, ValueError):
            return self._reject(pair_hash, "SOURCE_SAFETY_REJECT")

        timestamp = source.get("reconstruction", {}).get("target_B_timestamps", {}).get(
            target_id, {}
        )
        timestamp_pass = (
            isinstance(source.get("commit_timestamp_epoch"), int)
            and isinstance(timestamp.get("epoch"), int)
            and source["commit_timestamp_epoch"] <= timestamp["epoch"]
        )
        task_matrix = target["task_matrix"]
        security = target["focal_security_matrix"]
        findings = {
            "Q5": pstar["material_procedural_relevance"]["status"] == "PASS",
            "Q8": pstar["target_status_evidence"]["status"] in TARGET_STATUS_VALUES
            and pstar["target_status_evidence"]["finding"]["status"] == "PASS",
            "Q10": pstar["source_target_alignment_apart_from_pstar"]["status"] == "PASS",
            "Q11": pstar["no_second_comparably_material_incompatibility"]["status"]
            == "PASS",
        }
        booleans = {
            "Q1": bool(source.get("repository_commit")) and pstar["source_truth_evidence"]["execution"]["status"] == "PASS",
            "Q2": timestamp_pass,
            "Q3": pstar["source_truth_evidence"]["execution"]["status"] == "PASS",
            "Q4": bool(source.get("source_task_description")) and bool(source.get("source_implementation_or_patch")),
            **findings,
            "Q6": pstar["reviewer_decision"] == "PASS",
            "Q7": pstar["source_truth_evidence"]["status"] == "TRUE",
            "Q9": pstar["source_truth_evidence"]["execution"]["status"] == "PASS",
            "Q12": all(task_matrix[name] == "FAIL" for name in task_matrix if name.startswith("B_")),
            "Q13": task_matrix["U"] == "PASS" and security["U"] == "FAIL",
            "Q14": task_matrix["R"] == "PASS" and security["R"] == "PASS",
            "Q15": lock_valid,
            "Q16": cue["public_text_eligible"] is True,
        }
        answers = {question: "YES" if booleans[question] else "NO" for question in PAIR_REVIEW_QUESTIONS}
        decision = "ACCEPT" if all(answer == "YES" for answer in answers.values()) else "REJECT"
        terminal = "ELIGIBLE_PAIR_FROZEN" if decision == "ACCEPT" else (
            "TOP_SOURCE_TIMESTAMP_REJECT" if not timestamp_pass else "SEALED_PAIR_REVIEW_REJECT"
        )
        evidence_hashes = {
            "task_cue": stable_record_hash(cue),
            "source_corpus": FROZEN_SOURCE_CORPUS_SHA256,
            "target_execution": stable_record_hash(target),
            "artifact_bound_pstar": pstar["evidence_sha256"],
            "content_access_chain": self._audit.verify_chain(),
        }
        return {
            "decision": decision,
            "review_answers": answers,
            "evidence_hashes": evidence_hashes,
            "terminal_reason": terminal,
            "pair_hash": pair_hash,
        }


TARGET_STATUS_VALUES = frozenset({"FALSE", "UNJUSTIFIED"})


def frozen_target_order(
    instance_ids: Sequence[str], *, additional_development_exclusions: Sequence[str] = ()
) -> tuple[str, ...]:
    exclusions = set(DEVELOPMENT_IDS) | set(additional_development_exclusions)
    values = [value for value in instance_ids if value not in exclusions]
    if len(values) != len(set(values)):
        raise ProductionV4Error("target universe contains duplicate IDs")
    return tuple(
        sorted(
            values,
            key=lambda value: (
                hashlib.sha256(TARGET_ORDER_DOMAIN + b"\0" + value.encode("utf-8")).digest(),
                value,
            ),
        )
    )


class ScreeningLedgerV4:
    """Durable sequential decision barrier with immutable terminal reasons."""

    def __init__(self, database: Path, *, ordered_targets: Sequence[str]) -> None:
        self.database = Path(database).resolve()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.ordered_targets = tuple(ordered_targets)
        if not self.ordered_targets or len(set(self.ordered_targets)) != len(self.ordered_targets):
            raise ProductionV4Error("frozen target order is empty or duplicated")
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS screening_meta (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    ordered_targets_sha256 TEXT NOT NULL,
                    target_n INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS screening_attempt (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    logical_position INTEGER NOT NULL,
                    target_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    evidence_sha256 TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS screening_decision (
                    logical_position INTEGER PRIMARY KEY,
                    target_id TEXT NOT NULL UNIQUE,
                    decision TEXT NOT NULL CHECK(decision IN ('ELIGIBLE', 'REJECT', 'TECHNICAL_INVALID')),
                    terminal_reason TEXT NOT NULL,
                    evidence_sha256 TEXT NOT NULL,
                    eligible_count INTEGER NOT NULL,
                    previous_decision_sha256 TEXT NOT NULL,
                    decision_sha256 TEXT NOT NULL UNIQUE
                );
                CREATE TRIGGER IF NOT EXISTS screening_attempt_no_update
                BEFORE UPDATE ON screening_attempt BEGIN SELECT RAISE(ABORT, 'attempt ledger is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS screening_attempt_no_delete
                BEFORE DELETE ON screening_attempt BEGIN SELECT RAISE(ABORT, 'attempt ledger is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS screening_decision_no_update
                BEFORE UPDATE ON screening_decision BEGIN SELECT RAISE(ABORT, 'decision ledger is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS screening_decision_no_delete
                BEFORE DELETE ON screening_decision BEGIN SELECT RAISE(ABORT, 'decision ledger is append-only'); END;
                """
            )
            digest = stable_record_hash(list(self.ordered_targets))
            row = connection.execute("SELECT ordered_targets_sha256, target_n FROM screening_meta WHERE singleton = 1").fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO screening_meta VALUES (1, ?, ?)", (digest, TARGET_N)
                )
            elif tuple(row) != (digest, TARGET_N):
                raise ProductionV4Error("durable ledger target order or target N changed")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=60)
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def decisions(self) -> tuple[dict[str, Any], ...]:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            return tuple(
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM screening_decision ORDER BY logical_position"
                )
            )

    def record_attempt(
        self,
        *,
        logical_position: int,
        target_id: str,
        stage: str,
        status: str,
        evidence_sha256: str,
    ) -> None:
        if self.should_stop():
            raise ProductionV4Error("screening is already stopped")
        expected_position = len(self.decisions()) + 1
        if logical_position != expected_position or target_id != self.ordered_targets[logical_position - 1]:
            raise ProductionV4Error("attempt violates the ordered publication barrier")
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO screening_attempt (logical_position, target_id, stage, status, evidence_sha256) VALUES (?, ?, ?, ?, ?)",
                (logical_position, target_id, stage, status, evidence_sha256),
            )

    def record_decision(
        self,
        *,
        logical_position: int,
        target_id: str,
        decision: str,
        terminal_reason: str,
        evidence_sha256: str,
    ) -> dict[str, Any]:
        if terminal_reason not in TERMINAL_REASONS:
            raise ProductionV4Error("unknown terminal attrition reason")
        if decision not in {"ELIGIBLE", "REJECT", "TECHNICAL_INVALID"}:
            raise ProductionV4Error("unknown terminal decision")
        if (decision == "ELIGIBLE") != (terminal_reason == "ELIGIBLE_PAIR_FROZEN"):
            raise ProductionV4Error("eligible decision and terminal reason disagree")
        existing = self.decisions()
        if self.should_stop():
            raise ProductionV4Error("screening is already stopped")
        expected_position = len(existing) + 1
        if logical_position != expected_position or target_id != self.ordered_targets[logical_position - 1]:
            raise ProductionV4Error("cannot skip an earlier unresolved target")
        eligible_count = sum(row["decision"] == "ELIGIBLE" for row in existing) + (
            decision == "ELIGIBLE"
        )
        previous = "0" * 64 if not existing else str(existing[-1]["decision_sha256"])
        body = {
            "logical_position": logical_position,
            "target_id": target_id,
            "decision": decision,
            "terminal_reason": terminal_reason,
            "evidence_sha256": evidence_sha256,
            "eligible_count": int(eligible_count),
            "previous_decision_sha256": previous,
        }
        digest = stable_record_hash(body)
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO screening_decision VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (*body.values(), digest),
            )
        return {**body, "decision_sha256": digest}

    def should_stop(self) -> bool:
        decisions = self.decisions()
        return (
            sum(row["decision"] == "ELIGIBLE" for row in decisions) >= TARGET_N
            or len(decisions) == len(self.ordered_targets)
        )

    def stop_reason(self) -> str | None:
        if not self.should_stop():
            return None
        decisions = self.decisions()
        if sum(row["decision"] == "ELIGIBLE" for row in decisions) >= TARGET_N:
            return "TARGET_N_REACHED"
        return "TARGET_UNIVERSE_EXHAUSTED"
