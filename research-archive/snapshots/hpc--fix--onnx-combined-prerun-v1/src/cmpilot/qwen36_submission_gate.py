"""Canonical CPU-gate identity shared by Qwen3.6 generation and submission."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from .qwen36_candidate import canonical_json_bytes, sha256_file
from .qwen36_qualification import (
    Qwen36QualificationError,
    validate_seed_schedule,
)


SUBMISSION_GATE = Path("qualification/qwen36-v1/submission-gate.json")
SCHEMA = "qwen36-qualification-submission-gate-v1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise Qwen36QualificationError(f"submission gate {label} must be an object")
    return value


def _relative_file(project: Path, item: dict[str, Any], label: str) -> Path:
    raw = item.get("path")
    if not isinstance(raw, str) or not raw or Path(raw).is_absolute():
        raise Qwen36QualificationError(
            f"submission gate {label} path must be project-relative"
        )
    path = (project / raw).resolve(strict=True)
    try:
        path.relative_to(project)
    except ValueError as error:
        raise Qwen36QualificationError(
            f"submission gate {label} escapes the project"
        ) from error
    return path


def _expected_digest(item: dict[str, Any], label: str) -> str:
    value = item.get("sha256")
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise Qwen36QualificationError(
            f"submission gate {label} has an invalid SHA-256"
        )
    return value


def validate_submission_gate(
    project: Path,
    record_path: Path | None = None,
) -> dict[str, Any]:
    """Validate the one immutable gate record consumed by both launch paths."""
    project = project.resolve(strict=True)
    path = (record_path or project / SUBMISSION_GATE).resolve(strict=True)
    raw = path.read_bytes()
    try:
        record = json.loads(raw)
    except json.JSONDecodeError as error:
        raise Qwen36QualificationError("submission gate is not valid JSON") from error
    if not isinstance(record, dict):
        raise Qwen36QualificationError("submission gate must be a JSON object")
    if raw != canonical_json_bytes(record):
        raise Qwen36QualificationError("submission gate is not canonical JSON")

    freeze = _mapping(record.get("scientific_freeze"), "scientific_freeze")
    seeds = _mapping(record.get("seed_schedule"), "seed_schedule")
    suite = _mapping(record.get("suite_reference"), "suite_reference")
    amendment = _mapping(
        record.get("infrastructure_amendment"), "infrastructure_amendment"
    )
    cpu = _mapping(record.get("cpu_gate_result"), "cpu_gate_result")
    freeze_path = _relative_file(project, freeze, "scientific_freeze")
    seed_path = _relative_file(project, seeds, "seed_schedule")
    suite_path = _relative_file(project, suite, "suite_reference")
    amendment_path = _relative_file(
        project, amendment, "infrastructure_amendment"
    )
    cpu_raw_path = cpu.get("path")
    if not isinstance(cpu_raw_path, str) or not Path(cpu_raw_path).is_absolute():
        raise Qwen36QualificationError(
            "submission gate CPU result path must be absolute shared storage"
        )
    cpu_path = Path(cpu_raw_path).resolve(strict=True)
    expected = {
        "cpu_gate_result": _expected_digest(cpu, "cpu_gate_result"),
        "infrastructure_amendment": _expected_digest(
            amendment, "infrastructure_amendment"
        ),
        "scientific_freeze": _expected_digest(freeze, "scientific_freeze"),
        "seed_schedule": _expected_digest(seeds, "seed_schedule"),
        "suite_reference": _expected_digest(suite, "suite_reference"),
    }
    actual = {
        "cpu_gate_result": sha256_file(cpu_path),
        "infrastructure_amendment": sha256_file(amendment_path),
        "scientific_freeze": sha256_file(freeze_path),
        "seed_schedule": sha256_file(seed_path),
        "suite_reference": sha256_file(suite_path),
    }
    cpu_record = json.loads(cpu_path.read_text(encoding="utf-8"))
    schedule = validate_seed_schedule(seed_path)["seeds"]
    validated_commit = record.get("validated_source_commit")
    checks = {
        "canonical_json": raw == canonical_json_bytes(record),
        "schema": record.get("schema") == SCHEMA,
        "status": record.get("status") == "PASS",
        "digests": actual == expected,
        "validated_source_commit": isinstance(validated_commit, str)
        and _COMMIT.fullmatch(validated_commit) is not None,
        "cpu_gate_pass": isinstance(cpu_record, dict)
        and cpu_record.get("overall") == "PASS"
        and bool(cpu_record.get("checks"))
        and all(cpu_record.get("checks", {}).values()),
        "cpu_gate_freeze": cpu_record.get("qualification_freeze_sha256")
        == expected["scientific_freeze"],
        "cpu_gate_amendment": cpu_record.get("infrastructure_amendment_sha256")
        == expected["infrastructure_amendment"],
        "cpu_gate_suite": cpu_record.get("suite_reference_sha256")
        == expected["suite_reference"],
        "cpu_gate_seeds": cpu_record.get("seeds") == schedule,
    }
    if not all(checks.values()):
        raise Qwen36QualificationError(f"invalid canonical submission gate: {checks}")
    return {
        "checks": checks,
        "cpu_gate_record": cpu_record,
        "cpu_gate_result_path": cpu_path,
        "cpu_gate_result_sha256": actual["cpu_gate_result"],
        "infrastructure_amendment_path": amendment_path,
        "infrastructure_amendment_sha256": actual["infrastructure_amendment"],
        "pass": True,
        "record": record,
        "record_path": path,
        "record_sha256": sha256_file(path),
        "scientific_freeze_path": freeze_path,
        "scientific_freeze_sha256": actual["scientific_freeze"],
        "seed_schedule_path": seed_path,
        "seed_schedule_sha256": actual["seed_schedule"],
        "seeds": schedule,
        "suite_reference_path": suite_path,
        "suite_reference_sha256": actual["suite_reference"],
    }


def batch_gate_equivalence(
    text: str,
    *,
    gate: dict[str, Any],
    task_id: str,
    seed: int,
) -> dict[str, bool]:
    """Compare one rendered batch's attestation fields to the canonical record."""
    assignments: dict[str, list[str]] = {}
    names = (
        "SUBMISSION_GATE_RECORD",
        "EXPECTED_SUBMISSION_GATE_SHA256",
        "CPU_GATE",
        "EXPECTED_CPU_GATE_SHA256",
        "EXPECTED_AMENDMENT_SHA256",
        "EXPECTED_FREEZE_SHA256",
        "EXPECTED_SEED_SCHEDULE_SHA256",
        "EXPECTED_SUITE_REFERENCE_SHA256",
        "TASK_ID",
        "TASK_SEED",
    )
    for name in names:
        assignments[name] = re.findall(rf"^{name}=(.*)$", text, re.MULTILINE)
    record_relative = gate["record_path"].relative_to(
        Path(gate["record_path"]).parents[2]
    )
    expected = {
        "SUBMISSION_GATE_RECORD": f"$PROJECT/{record_relative.as_posix()}",
        "EXPECTED_SUBMISSION_GATE_SHA256": gate["record_sha256"],
        "CPU_GATE": str(gate["cpu_gate_result_path"]),
        "EXPECTED_CPU_GATE_SHA256": gate["cpu_gate_result_sha256"],
        "EXPECTED_AMENDMENT_SHA256": gate[
            "infrastructure_amendment_sha256"
        ],
        "EXPECTED_FREEZE_SHA256": gate["scientific_freeze_sha256"],
        "EXPECTED_SEED_SCHEDULE_SHA256": gate["seed_schedule_sha256"],
        "EXPECTED_SUITE_REFERENCE_SHA256": gate["suite_reference_sha256"],
        "TASK_ID": task_id,
        "TASK_SEED": str(seed),
    }
    checks = {
        name.lower(): assignments[name] == [value]
        for name, value in expected.items()
    }
    checks["runtime_gate_record_hash"] = (
        'sha256sum "$SUBMISSION_GATE_RECORD"' in text
        and '"$EXPECTED_SUBMISSION_GATE_SHA256"' in text
    )
    checks["runtime_cpu_gate_hash"] = (
        'sha256sum "$CPU_GATE"' in text
        and '"$EXPECTED_CPU_GATE_SHA256"' in text
    )
    checks["runtime_scientific_hashes"] = all(
        marker in text
        for marker in (
            '"$EXPECTED_AMENDMENT_SHA256"',
            '"$EXPECTED_FREEZE_SHA256"',
            '"$EXPECTED_SEED_SCHEDULE_SHA256"',
            '"$EXPECTED_SUITE_REFERENCE_SHA256"',
        )
    )
    return checks


__all__ = [
    "SUBMISSION_GATE",
    "batch_gate_equivalence",
    "validate_submission_gate",
]
