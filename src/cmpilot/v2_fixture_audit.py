"""Validate the prospective V2 execution-fixture construction audit."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA = "cmpilot-v2-fixture-construction-audit-v1"
FAMILIES = (
    "mcp-pinot-v1",
    "onnx-v1",
    "axios-v1",
    "aim-v1",
    "httpx-v1",
    "djoser-v1",
)


class FixtureAuditError(RuntimeError):
    """The prospective fixture audit is incomplete or inconsistent."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise FixtureAuditError(f"expected a JSON object: {path}")
    return value


def validate_fixture_audit(repository_root: Path, manifest_path: Path) -> dict[str, Any]:
    repository_root = Path(repository_root)
    manifest = _load(Path(manifest_path))
    if manifest.get("schema") != SCHEMA:
        raise FixtureAuditError("unexpected fixture-audit schema")
    families = manifest.get("families")
    if not isinstance(families, dict) or tuple(families) != FAMILIES:
        raise FixtureAuditError("fixture audit must contain the ordered six frozen families")
    if manifest.get("historical_family_is_execution_fixture") is not False:
        raise FixtureAuditError("historical family and V2 execution fixture were conflated")

    for family, row in families.items():
        root = repository_root / "families" / family
        package = _load(root / "family-package.json")
        transition = _load(root / "provenance/historical-transition.json")
        task = root / "tasks/target-task.md"
        memory_path = root / str(package["inputs"]["source_memory"]["path"])
        if row.get("historical_family_id") != package.get("family_id"):
            raise FixtureAuditError(f"family identity mismatch: {family}")
        if row.get("historical_revisions") != {
            "source": package.get("source_revision"),
            "compatible": package.get("compatible_revision"),
            "invalidated": package.get("target_revision"),
        }:
            raise FixtureAuditError(f"historical revision mismatch: {family}")
        if row.get("task_sha256") != _sha256(task):
            raise FixtureAuditError(f"task bytes changed: {family}")
        if row.get("source_memory_sha256") != _sha256(memory_path):
            raise FixtureAuditError(f"source memory bytes changed: {family}")
        expected_memory = package["inputs"]["source_memory"]["sha256"]
        if row.get("source_memory_sha256") != expected_memory:
            raise FixtureAuditError(f"source memory no longer matches frozen package: {family}")

        values = {}
        for state in ("source", "compatible", "invalidated"):
            evidence = transition[state]
            value = evidence.get("frozen_property_value", evidence.get("property_value"))
            values[state] = value
        if values != {"source": True, "compatible": True, "invalidated": False}:
            raise FixtureAuditError(f"historical trust predicate mismatch: {family}")
        if row.get("historical_trust_predicate") != values:
            raise FixtureAuditError(f"recorded trust predicate mismatch: {family}")
        if row.get("model_outcome_information_used") is not False:
            raise FixtureAuditError(f"outcome information entered fixture design: {family}")
        if row.get("status") == "READY":
            required = (
                "v2_base_repository_sha256",
                "faithful_delta_sha256",
                "task_completion_endpoint_sha256",
            )
            if any(not row.get(key) for key in required):
                raise FixtureAuditError(f"ready fixture lacks frozen inputs: {family}")
        elif row.get("status") != "BLOCKED_NON_IDENTIFIABLE_FIXTURE":
            raise FixtureAuditError(f"unknown fixture status: {family}")
    return manifest
