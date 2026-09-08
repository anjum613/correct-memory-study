"""Artifact-bound p-star and pair-safety evidence for confirmatory V4."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any, Mapping

from cmpilot.content_audit_v4 import ArtifactRef, ContentAccessAudit, TreeRef
from cmpilot.source_pairing import PSTAR_ONTOLOGY, stable_record_hash


class ArtifactEvidenceV4Error(RuntimeError):
    """Artifact-bound evidence is incomplete, spoofable, or contradicted."""


ALLOWED_LEVELS = frozenset({"A", "B"})
TARGET_STATUSES = frozenset({"FALSE", "UNJUSTIFIED"})
PREDICATE_KINDS = frozenset(
    {
        "CONTAINS_EXACT",
        "ABSENT_EXACT",
        "PYTHON_CALLS_OPERATION_WITH_ASSERTION",
        "PATCH_TOUCHES_EXACT_PATHS",
    }
)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _contains_boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, Mapping):
        return any(_contains_boolean(item) for item in value.values())
    if isinstance(value, (tuple, list)):
        return any(_contains_boolean(item) for item in value)
    return False


def _validate_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ArtifactEvidenceV4Error(f"{name} must be exact non-empty text")


@dataclass(frozen=True)
class ArtifactPredicate:
    artifact_name: str
    kind: str
    value: str

    def __post_init__(self) -> None:
        _validate_text(self.artifact_name, "predicate artifact")
        _validate_text(self.value, "predicate value")
        if self.kind not in PREDICATE_KINDS:
            raise ArtifactEvidenceV4Error("unknown deterministic evidence predicate")


@dataclass(frozen=True)
class FindingSpec:
    finding: str
    predicates: tuple[ArtifactPredicate, ...]

    def __post_init__(self) -> None:
        if self.finding not in {
            "TARGET_PSTAR_MISMATCH",
            "MATERIAL_PROCEDURAL_RELEVANCE",
            "SOURCE_TARGET_ALIGNMENT_APART_FROM_PSTAR",
            "NO_SECOND_COMPARABLY_MATERIAL_INCOMPATIBILITY",
        }:
            raise ArtifactEvidenceV4Error("unknown structured pair finding")
        if not self.predicates:
            raise ArtifactEvidenceV4Error("structured pair finding has no predicates")


@dataclass(frozen=True)
class SourceExecutionSpec:
    tree: TreeRef
    argv: tuple[str, ...]
    environment: tuple[tuple[str, str], ...] = ()
    environment_identity: str = "FROZEN_SOURCE_ENVIRONMENT"
    timeout_seconds: int = 1200

    def __post_init__(self) -> None:
        if not self.argv or any(not isinstance(value, str) or not value for value in self.argv):
            raise ArtifactEvidenceV4Error("source test command is empty")
        _validate_text(self.environment_identity, "source environment identity")


@dataclass(frozen=True)
class PstarEvidenceSpec:
    proposition_text: str
    ontology_class: str
    source_objects: tuple[str, ...]
    target_objects: tuple[str, ...]
    operation: str
    boundary_or_condition: str
    level: str
    target_status: str
    source_artifacts: tuple[tuple[str, ArtifactRef], ...]
    target_artifacts: tuple[tuple[str, ArtifactRef], ...]
    source_code_artifact: str
    source_test_artifact: str
    source_boundary_predicates: tuple[ArtifactPredicate, ...]
    findings: tuple[FindingSpec, ...]
    source_execution: SourceExecutionSpec

    def __post_init__(self) -> None:
        for name, value in (
            ("proposition", self.proposition_text),
            ("operation", self.operation),
            ("boundary", self.boundary_or_condition),
        ):
            _validate_text(value, name)
        if self.ontology_class not in PSTAR_ONTOLOGY:
            raise ArtifactEvidenceV4Error("p-star ontology class is not frozen")
        if self.level not in ALLOWED_LEVELS:
            raise ArtifactEvidenceV4Error("old Level C is not confirmatory eligible")
        if self.target_status not in TARGET_STATUSES:
            raise ArtifactEvidenceV4Error("target p-star status must be FALSE or UNJUSTIFIED")
        if not self.source_objects or not self.target_objects:
            raise ArtifactEvidenceV4Error("p-star must name source and target objects")
        if any(not value.strip() for value in (*self.source_objects, *self.target_objects)):
            raise ArtifactEvidenceV4Error("p-star object names must be exact")
        source_names = [name for name, _ in self.source_artifacts]
        target_names = [name for name, _ in self.target_artifacts]
        if len(source_names) != len(set(source_names)) or len(target_names) != len(
            set(target_names)
        ):
            raise ArtifactEvidenceV4Error("artifact names are not unique")
        if set(source_names) & set(target_names):
            raise ArtifactEvidenceV4Error("source and target artifact names overlap")
        if self.source_code_artifact not in source_names or self.source_test_artifact not in source_names:
            raise ArtifactEvidenceV4Error("source code/test artifacts are not bound")
        if not self.source_boundary_predicates:
            raise ArtifactEvidenceV4Error("source boundary has no artifact predicate")
        findings = {finding.finding for finding in self.findings}
        if findings != {
            "TARGET_PSTAR_MISMATCH",
            "MATERIAL_PROCEDURAL_RELEVANCE",
            "SOURCE_TARGET_ALIGNMENT_APART_FROM_PSTAR",
            "NO_SECOND_COMPARABLY_MATERIAL_INCOMPATIBILITY",
        }:
            raise ArtifactEvidenceV4Error("the four target-side findings are not separate")


def _python_calls_operation_with_assertion(payload: bytes, operation: str) -> bool:
    try:
        tree = ast.parse(payload.decode("utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return False
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        candidate = node.func
        while isinstance(candidate, ast.Attribute):
            if candidate.attr == operation:
                calls.append(node)
                break
            candidate = candidate.value
        if isinstance(candidate, ast.Name) and candidate.id == operation:
            calls.append(node)
    assertion = any(isinstance(node, ast.Assert) for node in ast.walk(tree))
    assertion = assertion or any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr.startswith("assert")
        for node in ast.walk(tree)
    )
    return bool(calls) and assertion


def _patch_paths(text: str) -> tuple[str, ...]:
    values = []
    for line in text.splitlines():
        match = re.fullmatch(r"diff --git a/(.*?) b/(.*?)", line)
        if match:
            if match.group(1) != match.group(2):
                raise ArtifactEvidenceV4Error("renaming patch is not valid path evidence")
            values.append(match.group(1))
    return tuple(sorted(set(values)))


def _evaluate_predicate(predicate: ArtifactPredicate, artifacts: Mapping[str, bytes]) -> dict[str, Any]:
    if predicate.artifact_name not in artifacts:
        raise ArtifactEvidenceV4Error("predicate cites an artifact on the wrong side")
    payload = artifacts[predicate.artifact_name]
    text = payload.decode("utf-8", errors="strict")
    if predicate.kind == "CONTAINS_EXACT":
        passed = predicate.value in text
        observed = text.count(predicate.value)
    elif predicate.kind == "ABSENT_EXACT":
        passed = predicate.value not in text
        observed = text.count(predicate.value)
    elif predicate.kind == "PYTHON_CALLS_OPERATION_WITH_ASSERTION":
        passed = _python_calls_operation_with_assertion(payload, predicate.value)
        observed = 1 if passed else 0
    else:
        expected = tuple(sorted(value for value in predicate.value.split("\n") if value))
        actual = _patch_paths(text)
        passed = actual == expected
        observed = actual
    return {
        "artifact_name": predicate.artifact_name,
        "kind": predicate.kind,
        "value": predicate.value,
        "passed": passed,
        "observed": observed,
        "artifact_sha256": _sha(payload),
    }


def _execute_source_test(
    spec: SourceExecutionSpec,
    *,
    audit: ContentAccessAudit,
    target_id: str,
    source_id: str,
) -> dict[str, Any]:
    tree = audit.verify_tree(
        spec.tree,
        target_id=target_id,
        source_id=source_id,
        caller="artifact_evidence_v4._execute_source_test",
    )
    command = [value.replace("{tree}", str(tree)) for value in spec.argv]
    try:
        completed = subprocess.run(
            command,
            cwd=tree,
            env={**os.environ, **dict(spec.environment)},
            capture_output=True,
            timeout=spec.timeout_seconds,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as error:
        raise ArtifactEvidenceV4Error("source executable test infrastructure invalid") from error
    return {
        "command": command,
        "environment": spec.environment_identity,
        "exit_code": completed.returncode,
        "stdout_utf8": completed.stdout.decode("utf-8", errors="replace"),
        "stderr_utf8": completed.stderr.decode("utf-8", errors="replace"),
        "stdout_sha256": _sha(completed.stdout),
        "stderr_sha256": _sha(completed.stderr),
        "tree_sha256": spec.tree.sha256,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
    }


def verify_artifact_bound_pstar(
    *,
    spec: PstarEvidenceSpec,
    audit: ContentAccessAudit,
    target_id: str,
    source_id: str,
    pair_hash: str,
) -> dict[str, Any]:
    """Independently derive source truth and all target-side pair findings."""

    if not isinstance(spec, PstarEvidenceSpec):
        raise ArtifactEvidenceV4Error("p-star evidence requires a typed artifact spec")
    if _contains_boolean(spec):
        raise ArtifactEvidenceV4Error("arbitrary boolean evidence is prohibited")
    if not re.fullmatch(r"[0-9a-f]{64}", pair_hash):
        raise ArtifactEvidenceV4Error("pair hash is invalid")
    source_refs = dict(spec.source_artifacts)
    target_refs = dict(spec.target_artifacts)
    source_payloads = {
        name: audit.read_bytes(
            artifact,
            target_id=target_id,
            source_id=source_id,
            caller="artifact_evidence_v4.verify_artifact_bound_pstar.source",
        )
        for name, artifact in source_refs.items()
    }
    target_payloads = {
        name: audit.read_bytes(
            artifact,
            target_id=target_id,
            source_id=source_id,
            caller="artifact_evidence_v4.verify_artifact_bound_pstar.target",
        )
        for name, artifact in target_refs.items()
    }

    code = source_payloads[spec.source_code_artifact].decode("utf-8", errors="strict")
    if not re.search(rf"\b{re.escape(spec.operation)}\b", code):
        raise ArtifactEvidenceV4Error("named operation is absent from source code artifact")
    test_call = ArtifactPredicate(
        spec.source_test_artifact,
        "PYTHON_CALLS_OPERATION_WITH_ASSERTION",
        spec.operation,
    )
    source_predicates = [
        _evaluate_predicate(predicate, source_payloads)
        for predicate in (*spec.source_boundary_predicates, test_call)
    ]
    if not all(result["passed"] for result in source_predicates):
        raise ArtifactEvidenceV4Error("source proposition is not established by artifacts")
    if spec.level == "A" and not any(
        predicate.artifact_name == spec.source_test_artifact
        and predicate.kind == "CONTAINS_EXACT"
        for predicate in spec.source_boundary_predicates
    ):
        raise ArtifactEvidenceV4Error("Level A test does not directly exercise the boundary")
    if spec.level == "B" and not any(
        predicate.artifact_name == spec.source_code_artifact
        for predicate in spec.source_boundary_predicates
    ):
        raise ArtifactEvidenceV4Error("Level B source code does not establish the invariant")
    execution = _execute_source_test(
        spec.source_execution,
        audit=audit,
        target_id=target_id,
        source_id=source_id,
    )
    if execution["status"] != "PASS":
        raise ArtifactEvidenceV4Error("source executable test did not pass")

    findings: dict[str, Any] = {}
    combined = {**source_payloads, **target_payloads}
    for finding in spec.findings:
        results = [_evaluate_predicate(predicate, combined) for predicate in finding.predicates]
        cited_sides = {
            "SOURCE" if predicate.artifact_name in source_payloads else "TARGET"
            for predicate in finding.predicates
        }
        if finding.finding in {
            "MATERIAL_PROCEDURAL_RELEVANCE",
            "SOURCE_TARGET_ALIGNMENT_APART_FROM_PSTAR",
        } and cited_sides != {"SOURCE", "TARGET"}:
            raise ArtifactEvidenceV4Error(
                f"{finding.finding} must bind both source and target artifacts"
            )
        findings[finding.finding] = {
            "status": "PASS" if all(result["passed"] for result in results) else "FAIL",
            "predicate_results": results,
            "evidence_sha256": stable_record_hash(results),
        }

    source_artifacts = {
        name: {
            "path": artifact.relative_path,
            "allowed_boundary": artifact.boundary,
            "sha256": artifact.sha256,
        }
        for name, artifact in source_refs.items()
    }
    target_artifacts = {
        name: {
            "path": artifact.relative_path,
            "allowed_boundary": artifact.boundary,
            "sha256": artifact.sha256,
        }
        for name, artifact in target_refs.items()
    }
    record = {
        "schema": "cmpilot-artifact-bound-pstar-v4",
        "target_id": target_id,
        "source_id": source_id,
        "pair_hash": pair_hash,
        "proposition_text": spec.proposition_text,
        "ontology_class": spec.ontology_class,
        "source_objects": list(spec.source_objects),
        "target_objects": list(spec.target_objects),
        "operation": spec.operation,
        "boundary_or_condition": spec.boundary_or_condition,
        "source_artifacts": source_artifacts,
        "target_artifacts": target_artifacts,
        "source_truth_evidence": {
            "status": "TRUE",
            "level": spec.level,
            "predicate_results": source_predicates,
            "execution": execution,
        },
        "target_status_evidence": {
            "status": spec.target_status,
            "finding": findings["TARGET_PSTAR_MISMATCH"],
        },
        "material_procedural_relevance": findings["MATERIAL_PROCEDURAL_RELEVANCE"],
        "source_target_alignment_apart_from_pstar": findings[
            "SOURCE_TARGET_ALIGNMENT_APART_FROM_PSTAR"
        ],
        "no_second_comparably_material_incompatibility": findings[
            "NO_SECOND_COMPARABLY_MATERIAL_INCOMPATIBILITY"
        ],
        "commands_used": [execution["command"]],
        "outputs": [
            {
                "stdout_utf8": execution["stdout_utf8"],
                "stderr_utf8": execution["stderr_utf8"],
                "exit_code": execution["exit_code"],
            }
        ],
        "output_hashes": [
            {
                "stdout_sha256": execution["stdout_sha256"],
                "stderr_sha256": execution["stderr_sha256"],
            }
        ],
        "reviewer_decision": "PASS"
        if all(finding["status"] == "PASS" for finding in findings.values())
        else "REJECT",
        "reviewer": "DETERMINISTIC_ARTIFACT_VERIFIER_V4",
        "arbitrary_boolean_attestation_accepted": False,
    }
    record["evidence_sha256"] = stable_record_hash(record)
    return record
