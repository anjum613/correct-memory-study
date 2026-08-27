"""Deterministic, objective tables for the frozen final experiment.

The lower-level :mod:`cmpilot.final_experiment` aggregation deliberately keeps
an inventory row for every planned atomic run.  This module turns that inventory
into a flat analysis table without dropping absent or interrupted runs, and can
optionally fail closed until every total-finalizer artifact is complete.
"""

from __future__ import annotations

from collections.abc import Mapping
import csv
import io
import json
import os
from pathlib import Path
from typing import Any

from .final_experiment import (
    FinalExperimentError,
    aggregate_run_results,
    sha256_bytes,
    validate_run_matrix,
    write_new_canonical_json,
)


REPORT_SCHEMA = "cmpilot-final-analysis-table-v1"

CSV_COLUMNS = (
    "run_id",
    "attempt_state",
    "model",
    "model_profile",
    "model_revision",
    "family",
    "condition",
    "repetition",
    "seed",
    "functionality_outcome",
    "functionality_result_json",
    "security_witness_outcome",
    "security_witness_result_json",
    "final_classification",
    "classification_json",
    "termination_reason",
    "technical_validity",
    "action_count",
    "model_request_count",
    "elapsed_time_seconds",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "token_statistics_json",
    "memory_provenance_identifier",
    "memory_content_sha256",
    "task_revision",
    "source_revision",
    "slurm_job_id",
    "completed_attempt",
    "result_sha256",
    "classification_sha256",
)


class FinalReportingError(FinalExperimentError):
    """A completed artifact inventory cannot produce an objective table."""


def _load_json_object(path: Path) -> dict[str, Any]:
    """Load one JSON object while rejecting duplicate keys and non-finite values."""

    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise FinalReportingError(f"duplicate JSON key in {path}: {key}")
            value[key] = item
        return value

    def constant(value: str) -> None:
        raise FinalReportingError(f"non-finite JSON number in {path}: {value}")

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=object_pairs,
            parse_constant=constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise FinalReportingError(f"cannot read completed result {path}: {error}") from error
    if not isinstance(value, dict):
        raise FinalReportingError(f"completed result is not a JSON object: {path}")
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _count(value: Any, *, name: str, run_id: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FinalReportingError(f"{run_id} has invalid {name}: {value!r}")
    return value


def _seconds(value: Any, *, run_id: str) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise FinalReportingError(
            f"{run_id} has invalid elapsed_time_seconds: {value!r}"
        )
    return value


def _token_statistics(result: Mapping[str, Any]) -> Mapping[str, Any] | None:
    value = result.get("token_usage")
    if value is None:
        return None
    if isinstance(value, Mapping):
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise FinalReportingError(f"invalid token statistics: {value!r}")
    return {"total_tokens": value}


def _token_count(
    token_statistics: Mapping[str, Any] | None,
    *names: str,
    run_id: str,
) -> int | None:
    if token_statistics is None:
        return None
    for name in names:
        if name in token_statistics and token_statistics[name] is not None:
            return _count(
                token_statistics[name], name=f"token statistic {name}", run_id=run_id
            )
    return None


def _objective_metrics(result: Mapping[str, Any], *, run_id: str) -> dict[str, Any]:
    tokens = _token_statistics(result)
    return {
        "action_count": _count(
            result.get("action_count"), name="action_count", run_id=run_id
        ),
        "completion_tokens": _token_count(
            tokens, "completion_tokens", "completion", run_id=run_id
        ),
        "elapsed_time_seconds": _seconds(
            result.get("elapsed_seconds"), run_id=run_id
        ),
        "model_request_count": _count(
            result.get("model_request_count"),
            name="model_request_count",
            run_id=run_id,
        ),
        "prompt_tokens": _token_count(tokens, "prompt_tokens", "prompt", run_id=run_id),
        "slurm_job_id": result.get("job_id"),
        "token_statistics": None if tokens is None else dict(tokens),
        "total_tokens": _token_count(
            tokens, "total_tokens", "total", run_id=run_id
        ),
    }


def _outcome(value: Any) -> str:
    record = _mapping(value)
    if record.get("pass") is True:
        return "PASS"
    if record.get("pass") is False:
        return "FAIL"
    return "UNAVAILABLE"


def _group_analysis_rows(
    rows: list[dict[str, Any]], *, source_key: str, output_key: str
) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row[source_key]), []).append(row)
    return [
        {
            output_key: name,
            "run_count": len(members),
            "attempt_states": {
                state: sum(row["attempt_state"] == state for row in members)
                for state in ("ABSENT", "INTERRUPTED", "COMPLETED")
            },
            "functionality": {
                outcome: sum(
                    row["functionality_outcome"] == outcome for row in members
                )
                for outcome in ("PASS", "FAIL", "UNAVAILABLE")
            },
            "security_witness": {
                outcome: sum(
                    row["security_witness_outcome"] == outcome for row in members
                )
                for outcome in ("PASS", "FAIL", "UNAVAILABLE")
            },
        }
        for name, members in sorted(groups.items())
    ]


def build_analysis_report(
    matrix: Any,
    output_root: Path,
    *,
    require_complete: bool = False,
) -> dict[str, Any]:
    """Build a stable flat table and retain explicit incomplete-run evidence."""

    matrix = validate_run_matrix(matrix)
    aggregation = aggregate_run_results(matrix, Path(output_root))
    runs_by_id = {run["run_id"]: run for run in matrix["runs"]}
    rows: list[dict[str, Any]] = []
    incomplete: list[dict[str, str]] = []
    for inventory in aggregation["runs"]:
        run_id = str(inventory["run_id"])
        run = runs_by_id[run_id]
        state = str(inventory["attempt_state"])
        result: Mapping[str, Any] = {}
        metrics = {
            "action_count": None,
            "completion_tokens": None,
            "elapsed_time_seconds": None,
            "model_request_count": None,
            "prompt_tokens": None,
            "slurm_job_id": None,
            "token_statistics": None,
            "total_tokens": None,
        }
        if state == "COMPLETED":
            attempt = Path(str(inventory["completed_attempt"]))
            result = _load_json_object(attempt / "result.json")
            metrics = _objective_metrics(result, run_id=run_id)
        else:
            incomplete.append({"run_id": run_id, "state": state})

        classification = inventory.get("classification")
        classification_record = _mapping(classification)
        final_classification = _first_present(
            result.get("final_classification"), classification_record.get("label")
        )
        if state == "COMPLETED" and (
            not isinstance(final_classification, str) or not final_classification
        ):
            raise FinalReportingError(
                f"completed run has no final classification label: {run_id}"
            )
        # ``witness_result`` is retained only for pre-v2 synthetic fixtures;
        # production final-run artifacts use ``security_witness_result``.
        witness_result = _first_present(
            result.get("security_witness_result"), inventory.get("witness_result")
        )
        rows.append(
            {
                "action_count": metrics["action_count"],
                "attempt_state": state,
                "classification": classification,
                "classification_sha256": inventory.get("classification_sha256"),
                "completed_attempt": inventory.get("completed_attempt"),
                "completion_tokens": metrics["completion_tokens"],
                "condition": run["condition"],
                "elapsed_time_seconds": metrics["elapsed_time_seconds"],
                "family": run["family_id"],
                "family_id": run["family_id"],
                "final_classification": final_classification,
                "functionality_outcome": inventory["functionality_outcome"],
                "functionality_result": inventory.get("functionality_result"),
                "memory_content_sha256": run.get("memory_content_sha256"),
                "memory_provenance_identifier": run.get(
                    "memory_provenance_manifest_sha256"
                ),
                "model": run["model_id"],
                "model_id": run["model_id"],
                "model_profile": run["model_profile"],
                "model_request_count": metrics["model_request_count"],
                "model_revision": run["model_revision"],
                "prompt_tokens": metrics["prompt_tokens"],
                "repetition": run["repetition"],
                "result_sha256": inventory.get("result_sha256"),
                "run_id": run_id,
                "security_witness_outcome": _outcome(witness_result),
                "security_witness_result": witness_result,
                "seed": run["seed"],
                "slurm_job_id": metrics["slurm_job_id"],
                "source_revision": run["source_revision"],
                "task_revision": run["target_revision"],
                "technical_validity": inventory.get("technical_validity"),
                "termination_reason": inventory.get("termination_reason"),
                "token_statistics": metrics["token_statistics"],
                "total_tokens": metrics["total_tokens"],
                "witness_outcome": _outcome(witness_result),
                "witness_result": witness_result,
            }
        )

    if require_complete and incomplete:
        counts = {
            state: sum(row["state"] == state for row in incomplete)
            for state in ("ABSENT", "INTERRUPTED")
        }
        raise FinalReportingError(
            "analysis table requires every planned run to be completed; "
            f"incomplete={len(incomplete)}, states={counts}"
        )

    return {
        "schema": REPORT_SCHEMA,
        "purpose": matrix["purpose"],
        "freeze_status": matrix["freeze_status"],
        "protocol_version": matrix["protocol_version"],
        "experiment_manifest_sha256": matrix["experiment_manifest_sha256"],
        "run_ids_sha256": matrix["run_ids_sha256"],
        "memory_mode": matrix["memory_mode"],
        "family_count_policy": matrix["family_count_policy"],
        "achieved_family_count": matrix["achieved_family_count"],
        "achieved_trust_category_coverage": matrix[
            "achieved_trust_category_coverage"
        ],
        "dimensions": matrix["dimensions"],
        "run_count": len(rows),
        "completed_run_count": len(rows) - len(incomplete),
        "incomplete_run_count": len(incomplete),
        "incomplete_runs": incomplete,
        "runs": rows,
        "inventory_summaries": {
            "by_condition": _group_analysis_rows(
                rows, source_key="condition", output_key="condition"
            ),
            "by_family": _group_analysis_rows(
                rows, source_key="family", output_key="family_id"
            ),
            "by_model": _group_analysis_rows(
                rows, source_key="model_profile", output_key="model_profile"
            ),
        },
    }


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (Mapping, list, tuple)):
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    return value


def render_analysis_csv(report: Mapping[str, Any]) -> bytes:
    """Render the report rows with a fixed, analysis-ready column order."""

    if report.get("schema") != REPORT_SCHEMA or not isinstance(report.get("runs"), list):
        raise FinalReportingError("analysis report has an unsupported schema")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in report["runs"]:
        if not isinstance(row, Mapping):
            raise FinalReportingError("analysis report contains a non-object row")
        csv_row = {
            "run_id": row.get("run_id"),
            "attempt_state": row.get("attempt_state"),
            "model": row.get("model"),
            "model_profile": row.get("model_profile"),
            "model_revision": row.get("model_revision"),
            "family": row.get("family"),
            "condition": row.get("condition"),
            "repetition": row.get("repetition"),
            "seed": row.get("seed"),
            "functionality_outcome": row.get("functionality_outcome"),
            "functionality_result_json": row.get("functionality_result"),
            "security_witness_outcome": row.get("security_witness_outcome"),
            "security_witness_result_json": row.get("security_witness_result"),
            "final_classification": row.get("final_classification"),
            "classification_json": row.get("classification"),
            "termination_reason": row.get("termination_reason"),
            "technical_validity": row.get("technical_validity"),
            "action_count": row.get("action_count"),
            "model_request_count": row.get("model_request_count"),
            "elapsed_time_seconds": row.get("elapsed_time_seconds"),
            "prompt_tokens": row.get("prompt_tokens"),
            "completion_tokens": row.get("completion_tokens"),
            "total_tokens": row.get("total_tokens"),
            "token_statistics_json": row.get("token_statistics"),
            "memory_provenance_identifier": row.get(
                "memory_provenance_identifier"
            ),
            "memory_content_sha256": row.get("memory_content_sha256"),
            "task_revision": row.get("task_revision"),
            "source_revision": row.get("source_revision"),
            "slurm_job_id": row.get("slurm_job_id"),
            "completed_attempt": row.get("completed_attempt"),
            "result_sha256": row.get("result_sha256"),
            "classification_sha256": row.get("classification_sha256"),
        }
        writer.writerow({key: _csv_value(value) for key, value in csv_row.items()})
    return stream.getvalue().encode("utf-8")


def _write_new_bytes(path: Path, payload: bytes) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError as error:
        raise FinalReportingError(f"refusing to overwrite existing artifact: {path}") from error
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return sha256_bytes(payload)


def write_analysis_outputs(
    json_path: Path,
    csv_path: Path,
    report: Mapping[str, Any],
) -> dict[str, str]:
    """Exclusively create the paired canonical JSON and CSV outputs."""

    json_path = Path(json_path)
    csv_path = Path(csv_path)
    if json_path == csv_path:
        raise FinalReportingError("JSON and CSV output paths must differ")
    existing = [path for path in (json_path, csv_path) if path.exists() or path.is_symlink()]
    if existing:
        raise FinalReportingError(
            f"refusing to overwrite existing artifact: {existing[0]}"
        )
    csv_payload = render_analysis_csv(report)
    json_created = False
    try:
        json_sha256 = write_new_canonical_json(json_path, report)
        json_created = True
        csv_sha256 = _write_new_bytes(csv_path, csv_payload)
    except BaseException:
        if json_created:
            json_path.unlink(missing_ok=True)
        raise
    return {"csv_sha256": csv_sha256, "json_sha256": json_sha256}


__all__ = [
    "CSV_COLUMNS",
    "FinalReportingError",
    "REPORT_SCHEMA",
    "build_analysis_report",
    "render_analysis_csv",
    "write_analysis_outputs",
]
