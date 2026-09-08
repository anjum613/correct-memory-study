"""Total, versioned finalization for calculator capability diagnostics.

The evaluated agent's termination reason is data.  It must never determine
whether repository capture, integrity checks, cleanup, and artifact
preservation run.  This module therefore owns run-level finalizer state in a
JSON record and chooses the process exit status only after every mandatory
stage has been attempted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, Mapping


FINALIZER_STATE_SCHEMA = "qwen32b-calculator-finalizer-state-v1"
FINALIZER_CONTROL_FLOW_VERSION = "calculator-finalizer-control-flow-v1"
LEGACY_SHELL_STATE_VERSION = "calculator-finalizer-shell-state-v1"

OPERATIONAL_FINALIZATION_STAGES = (
    "final_repository_capture",
    "patch_generation",
    "immutable_oracle",
    "source_integrity",
    "project_environment_cache_integrity",
    "shutdown",
    "scratch_cleanup",
    "performance_summary",
)

MANDATORY_FINALIZATION_STAGES = (
    *OPERATIONAL_FINALIZATION_STAGES,
    "result_json",
    "classification_json",
    "artifact_preservation",
    "manifest_generation",
    "manifest_validation",
    "authoritative_result",
)

TERMINATION_PATHS = (
    "NORMAL_COMPLETION",
    "STAGNATION_LIMIT",
    "CONTEXT_BUDGET_EXHAUSTED",
    "STEP_LIMIT",
    "REPEATED_INVALID_ACTION",
    "REPEATED_POLICY_VIOLATION",
    "MODEL_TASK_FAILURE",
    "PROTECTED_WRITE_SAFELY_REJECTED",
    "ANALYZER_TECHNICAL_VIOLATION",
    "TRANSPORT_FAILURE",
)

_MANIFEST_EXCLUDES = frozenset(
    {
        "artifact-preservation-idempotency.json",
        "finalizer-state.json",
        "manifest-validation.json",
        "sha256-manifest.txt",
    }
)

# These are the run-level status variables used by job 25692's post-agent
# shell.  Every one except POST_AGENT_FAILURE_COUNT was assigned before its
# first read.  The inventory helper deliberately keeps this historical set
# explicit so future generated scripts cannot silently add unreviewed shell
# state.
FINALIZER_SHELL_STATUS_VARIABLES = (
    "POST_AGENT_FAILURE_COUNT",
    "SERVER_PID",
    "GPU_MONITOR_PID",
    "PROCESS_MONITOR_PID",
    "FAIL_LABEL",
    "FAIL_MESSAGE",
    "SCRIPT_OBSERVATION_STATUS",
    "VERIFIER_BOOTSTRAP_STATUS",
    "MANIFEST_BOOTSTRAP_STATUS",
    "RUNTIME_SOURCE_STATUS",
    "PORT_STATUS",
    "SERVER_COMMAND_EXTRACTION_STATUS",
    "SMOKE_STATUS",
    "ANALYSIS_STATUS",
    "POLICY_AUDIT_STATUS",
    "FINAL_COLLECTION_STATUS",
    "PATCH_HASH_STATUS",
    "MINI_SOURCE_CAPTURE_STATUS",
    "MINI_SOURCE_COMPARE_STATUS",
    "SHUTDOWN_STATUS",
    "FINAL_PROCESS_STATUS",
    "FINAL_MINI_PROCESS_STATUS",
    "GPU_RELEASE_STATUS",
    "CACHE_FINAL_STATUS",
    "SOURCE_INTEGRITY_STATUS",
    "POST_FINGERPRINT_STATUS",
    "POST_CONTENT_STATUS",
    "PRESERVATION_STATUS",
    "SCRATCH_CLEANUP_STATUS",
    "FINAL_LABEL",
)


class CalculatorFinalizerError(RuntimeError):
    """Raised when finalizer state or shell control flow is invalid."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "as_dict"):
        return _json_value(value.as_dict())
    return repr(value)


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _write_json(path: Path, value: Any) -> None:
    payload = (
        json.dumps(_json_value(value), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")
    _atomic_write(path, payload)
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if parsed != _json_value(value):
        raise CalculatorFinalizerError(f"JSON round trip changed {path}")


@dataclass
class FinalizerState:
    """Structured state initialized before the evaluated agent starts."""

    run_id: str
    initialized_utc: str
    termination_reason: str = "PENDING"
    post_agent_failure_count: int = 0
    stage_statuses: dict[str, str] = field(
        default_factory=lambda: {
            name: "pending" for name in MANDATORY_FINALIZATION_STAGES
        }
    )
    stage_errors: dict[str, str] = field(default_factory=dict)
    final_exit_code: int | None = None
    final_exit_chosen_after_all_stages: bool = False
    schema: str = FINALIZER_STATE_SCHEMA

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "run_id": self.run_id,
            "initialized_utc": self.initialized_utc,
            "termination_reason": self.termination_reason,
            "post_agent_failure_count": self.post_agent_failure_count,
            "stage_statuses": dict(self.stage_statuses),
            "stage_errors": dict(self.stage_errors),
            "final_exit_code": self.final_exit_code,
            "final_exit_chosen_after_all_stages": (
                self.final_exit_chosen_after_all_stages
            ),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FinalizerState":
        if value.get("schema") != FINALIZER_STATE_SCHEMA:
            raise CalculatorFinalizerError("unsupported calculator finalizer state")
        statuses = value.get("stage_statuses")
        if not isinstance(statuses, dict) or set(statuses) != set(
            MANDATORY_FINALIZATION_STAGES
        ):
            raise CalculatorFinalizerError("finalizer stage inventory is incomplete")
        state = cls(
            run_id=str(value["run_id"]),
            initialized_utc=str(value["initialized_utc"]),
            termination_reason=str(value.get("termination_reason", "PENDING")),
            post_agent_failure_count=int(
                value.get("post_agent_failure_count", 0)
            ),
            stage_statuses={str(key): str(item) for key, item in statuses.items()},
            stage_errors={
                str(key): str(item)
                for key, item in dict(value.get("stage_errors", {})).items()
            },
            final_exit_code=(
                None
                if value.get("final_exit_code") is None
                else int(value["final_exit_code"])
            ),
            final_exit_chosen_after_all_stages=bool(
                value.get("final_exit_chosen_after_all_stages", False)
            ),
        )
        if state.post_agent_failure_count < 0:
            raise CalculatorFinalizerError("finalizer failure count cannot be negative")
        return state

    def record_stage(
        self, name: str, *, passed: bool, error: BaseException | str | None = None
    ) -> None:
        if name not in self.stage_statuses:
            raise CalculatorFinalizerError(f"unknown finalizer stage: {name}")
        if self.stage_statuses[name] != "pending":
            raise CalculatorFinalizerError(f"finalizer stage ran twice: {name}")
        self.stage_statuses[name] = "passed" if passed else "failed"
        if not passed:
            self.post_agent_failure_count += 1
            if error is not None:
                self.stage_errors[name] = (
                    f"{type(error).__name__}: {error}"
                    if isinstance(error, BaseException)
                    else str(error)
                )


def initialize_finalizer_state(path: Path, *, run_id: str) -> FinalizerState:
    """Create the authoritative state before any model action is accepted."""
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"finalizer state already exists: {path}")
    state = FinalizerState(run_id=run_id, initialized_utc=_utc_now())
    _write_json(path, state.as_dict())
    return state


def load_finalizer_state(path: Path) -> FinalizerState:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CalculatorFinalizerError("finalizer state must be a JSON object")
    return FinalizerState.from_dict(value)


def save_finalizer_state(path: Path, state: FinalizerState) -> None:
    _write_json(path, state.as_dict())


def render_legacy_shell_state_initialization() -> str:
    """Render the one compatibility counter used by the job-25692 shell.

    New structured state belongs in finalizer-state.json.  This line exists so
    a legacy generated batch script cannot fail under ``set -u`` while it is
    being migrated to the Python-owned state.
    """
    return (
        f"# {LEGACY_SHELL_STATE_VERSION}\n"
        "POST_AGENT_FAILURE_COUNT=0\n"
    )


def _shell_variable_record(lines: list[str], variable: str) -> dict[str, Any]:
    escaped = re.escape(variable)
    assignment = re.compile(rf"^\s*(?:export\s+|readonly\s+)?{escaped}=(.*)$")
    declaration = re.compile(rf"^\s*(?:declare|local|typeset)(?:\s+-\w+)*\s+{escaped}(?:=|\s|$)")
    dollar_read = re.compile(
        r"\$(?:" + escaped + r"\b|\{" + escaped + r"(?:\}|[:?+\-]))"
    )
    arithmetic_read = re.compile(rf"\(\([^\n]*\b{escaped}\b[^\n]*\)\)")
    declarations: list[int] = []
    assignments: list[int] = []
    initializations: list[int] = []
    increments: list[int] = []
    reads: list[int] = []
    for number, line in enumerate(lines, 1):
        if declaration.search(line):
            declarations.append(number)
        match = assignment.search(line)
        if match:
            assignments.append(number)
            right_hand_side = match.group(1)
            reads_self = bool(
                dollar_read.search(right_hand_side)
                or arithmetic_read.search(right_hand_side)
            )
            if reads_self:
                increments.append(number)
                reads.append(number)
            else:
                initializations.append(number)
            # Reads of the assigned variable on the left are handled above;
            # avoid counting the left-hand side itself as an arithmetic read.
            continue
        if dollar_read.search(line) or arithmetic_read.search(line):
            reads.append(number)
    first_read = min(reads) if reads else None
    first_initialization = min([*declarations, *initializations], default=None)
    guaranteed = first_read is None or (
        first_initialization is not None and first_initialization < first_read
    )
    return {
        "declaration_lines": declarations,
        "assignment_lines": assignments,
        "initialization_lines": initializations,
        "increment_lines": increments,
        "read_lines": sorted(set(reads)),
        "first_read_line": first_read,
        "first_initialization_line": first_initialization,
        "guaranteed_initialized_before_first_read": guaranteed,
    }


def inspect_shell_finalizer_control_flow(script: str) -> dict[str, Any]:
    """Inventory every known finalizer status variable in a generated script."""
    lines = script.splitlines()
    variables = {
        name: _shell_variable_record(lines, name)
        for name in FINALIZER_SHELL_STATUS_VARIABLES
    }
    used = {
        name: record
        for name, record in variables.items()
        if record["assignment_lines"]
        or record["declaration_lines"]
        or record["read_lines"]
    }
    potentially_unset = sorted(
        name
        for name, record in used.items()
        if not record["guaranteed_initialized_before_first_read"]
    )
    agent_lines = [
        number
        for number, line in enumerate(lines, 1)
        if "agent_start_ns=" in line or " -m cmpilot smoke" in line
    ]
    agent_start_line = min(agent_lines) if agent_lines else None
    legacy_initializations = variables["POST_AGENT_FAILURE_COUNT"][
        "initialization_lines"
    ]
    return {
        "schema": FINALIZER_CONTROL_FLOW_VERSION,
        "agent_start_line": agent_start_line,
        "legacy_counter_initialized_before_agent": bool(
            legacy_initializations
            and agent_start_line is not None
            and min(legacy_initializations) < agent_start_line
        ),
        "potentially_unset_variables": potentially_unset,
        "variables": used,
        "pass": not potentially_unset,
    }


def require_shell_finalizer_control_flow(script: str) -> dict[str, Any]:
    record = inspect_shell_finalizer_control_flow(script)
    if not record["pass"]:
        raise CalculatorFinalizerError(
            "generated calculator finalizer may read unset variables: "
            + ", ".join(record["potentially_unset_variables"])
        )
    if "POST_AGENT_FAILURE_COUNT" in record["variables"] and not record[
        "legacy_counter_initialized_before_agent"
    ]:
        raise CalculatorFinalizerError(
            "legacy finalizer counter must be initialized before agent execution"
        )
    return record


def insert_legacy_shell_state_initialization(script: str) -> str:
    """Return a corrected in-memory copy of a legacy generated script."""
    existing = inspect_shell_finalizer_control_flow(script)
    counter = existing["variables"].get("POST_AGENT_FAILURE_COUNT")
    if counter and counter["initialization_lines"]:
        return script
    lines = script.splitlines(keepends=True)
    marker = next(
        (
            index
            for index, line in enumerate(lines)
            if "agent_start_ns=" in line
        ),
        None,
    )
    if marker is None:
        raise CalculatorFinalizerError("agent start marker is missing")
    lines.insert(marker, render_legacy_shell_state_initialization())
    return "".join(lines)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_rows(artifact: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for path in sorted(artifact.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(artifact).as_posix()
        if (
            path.name in _MANIFEST_EXCLUDES
            or path.name.startswith("preservation-pass-")
        ):
            continue
        rows.append((_sha256_file(path), relative))
    return rows


def _preserve(artifact: Path, pass_number: int) -> dict[str, Any]:
    rows = _manifest_rows(artifact)
    text = "".join(f"{digest}  {relative}\n" for digest, relative in rows)
    _atomic_write(artifact / "sha256-manifest.txt", text.encode("utf-8"))
    inventory = hashlib.sha256(
        (json.dumps(rows, separators=(",", ":"), sort_keys=True) + "\n").encode(
            "utf-8"
        )
    ).hexdigest()
    record = {
        "pass_number": pass_number,
        "entry_count": len(rows),
        "inventory_sha256": inventory,
        "manifest_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
    _write_json(artifact / f"preservation-pass-{pass_number}.json", record)
    return record


def validate_self_excluding_manifest(artifact: Path) -> dict[str, Any]:
    manifest = artifact / "sha256-manifest.txt"
    errors: list[str] = []
    paths: set[str] = set()
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        paths.add(relative)
        path = artifact / relative
        if separator != "  " or not path.is_file() or _sha256_file(path) != digest:
            errors.append(relative or line)
    self_excluding = "sha256-manifest.txt" not in paths
    return {
        "pass": not errors and self_excluding,
        "errors": errors,
        "entry_count": len(paths),
        "manifest_sha256": _sha256_file(manifest),
        "self_excluding": self_excluding,
    }


StageCallback = Callable[[], Any]


@dataclass(frozen=True)
class TotalFinalizationOutcome:
    state: FinalizerState
    result: dict[str, Any]
    classification: dict[str, Any]
    operational_stage_results: dict[str, Any]
    manifest_validation: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.as_dict(),
            "result": self.result,
            "classification": self.classification,
            "operational_stage_results": self.operational_stage_results,
            "manifest_validation": self.manifest_validation,
        }


def run_total_finalization(
    *,
    state_path: Path,
    artifact_directory: Path,
    termination_reason: str,
    callbacks: Mapping[str, StageCallback],
    success_label: str,
    technical_failure_label: str,
    requested_exit_code: int,
    initial_technical_validity: bool,
    base_result: Mapping[str, Any] | None = None,
    classification_dimensions: Mapping[str, Any] | None = None,
) -> TotalFinalizationOutcome:
    """Attempt every mandatory stage and select one exit code at the end."""
    missing = sorted(set(OPERATIONAL_FINALIZATION_STAGES) - set(callbacks))
    extra = sorted(set(callbacks) - set(OPERATIONAL_FINALIZATION_STAGES))
    if missing or extra:
        raise CalculatorFinalizerError(
            f"operational finalizer callbacks mismatch: missing={missing}, extra={extra}"
        )
    state = load_finalizer_state(state_path)
    if state.final_exit_code is not None or any(
        status != "pending" for status in state.stage_statuses.values()
    ):
        raise CalculatorFinalizerError("finalizer state was already consumed")
    state.termination_reason = termination_reason
    save_finalizer_state(state_path, state)

    operational: dict[str, Any] = {}
    for name in OPERATIONAL_FINALIZATION_STAGES:
        callback = callbacks[name]
        try:
            value = callback()
        except BaseException as error:
            state.record_stage(name, passed=False, error=error)
            operational[name] = {
                "status": "failed",
                "error": f"{type(error).__name__}: {error}",
            }
        else:
            failed = isinstance(value, Mapping) and (
                value.get("pass") is False
                or value.get("complete") is False
                or value.get("technical_validity") == "fail"
            )
            state.record_stage(
                name,
                passed=not failed,
                error="stage returned a failing structured result" if failed else None,
            )
            operational[name] = {
                "status": "failed" if failed else "passed",
                "value": _json_value(value),
            }
        save_finalizer_state(state_path, state)

    _write_json(artifact_directory / "finalizer-operational-stages.json", operational)
    performance = operational.get("performance_summary", {})
    if performance.get("status") == "passed":
        performance_value = performance.get("value")
    else:
        performance_value = {
            "available": False,
            "error": performance.get("error", "performance summary unavailable"),
        }
    _write_json(
        artifact_directory / "performance-summary.json",
        {
            "schema": "qwen32b-calculator-performance-summary-v1",
            "termination_reason": termination_reason,
            "summary": performance_value,
        },
    )
    state.record_stage(
        "result_json", passed=True
    )  # Content is written immediately below.
    state.record_stage("classification_json", passed=True)
    state.record_stage("authoritative_result", passed=True)

    technical = initial_technical_validity and all(
        state.stage_statuses[name] == "passed"
        for name in OPERATIONAL_FINALIZATION_STAGES
    )
    label = success_label if technical else technical_failure_label
    result = dict(base_result or {})
    result.update(
        {
            "schema": "qwen32b-calculator-total-finalization-v1",
            "label": label,
            "pass": technical and requested_exit_code == 0,
            "technical_validity": "pass" if technical else "fail",
            "model_run_termination": termination_reason,
            "post_agent_failure_count": state.post_agent_failure_count,
            "mandatory_finalization_stages": list(MANDATORY_FINALIZATION_STAGES),
        }
    )
    dimensions = dict(classification_dimensions or {})
    dimensions.update(
        {
            "technical_validity": "pass" if technical else "fail",
            "model_run_termination": termination_reason,
            "post_agent_analysis_complete": (
                state.stage_statuses["final_repository_capture"] == "passed"
            ),
            "cleanup_complete": state.stage_statuses["scratch_cleanup"] == "passed",
        }
    )
    classification = {"label": label, "dimensions": dimensions}
    _write_json(artifact_directory / "result.json", result)
    _write_json(artifact_directory / "classification.json", classification)
    _atomic_write(
        artifact_directory / "authoritative-result.txt",
        f"{label}\n".encode("utf-8"),
    )

    preservation_error: BaseException | None = None
    manifest_validation: dict[str, Any] = {"pass": False, "errors": []}
    try:
        first = _preserve(artifact_directory, 1)
        second = _preserve(artifact_directory, 2)
        idempotency = {
            "pass": first["inventory_sha256"] == second["inventory_sha256"],
            "first": first,
            "second": second,
        }
        _write_json(
            artifact_directory / "artifact-preservation-idempotency.json",
            idempotency,
        )
        state.record_stage(
            "artifact_preservation",
            passed=bool(idempotency["pass"]),
            error=None if idempotency["pass"] else "preservation was not idempotent",
        )
        state.record_stage("manifest_generation", passed=True)
        manifest_validation = validate_self_excluding_manifest(artifact_directory)
        _write_json(
            artifact_directory / "manifest-validation.json", manifest_validation
        )
        state.record_stage(
            "manifest_validation",
            passed=bool(manifest_validation["pass"]),
            error=(
                None
                if manifest_validation["pass"]
                else "self-excluding manifest validation failed"
            ),
        )
    except BaseException as error:
        preservation_error = error
        for name in (
            "artifact_preservation",
            "manifest_generation",
            "manifest_validation",
        ):
            if state.stage_statuses[name] == "pending":
                state.record_stage(name, passed=False, error=error)

    all_stages_attempted = all(
        status != "pending" for status in state.stage_statuses.values()
    )
    final_technical = technical and preservation_error is None and all(
        status == "passed" for status in state.stage_statuses.values()
    )
    state.final_exit_code = requested_exit_code if final_technical else 1
    state.final_exit_chosen_after_all_stages = all_stages_attempted

    if not final_technical:
        result["label"] = technical_failure_label
        result["pass"] = False
        result["technical_validity"] = "fail"
        result["post_agent_failure_count"] = state.post_agent_failure_count
        classification["label"] = technical_failure_label
        classification["dimensions"]["technical_validity"] = "fail"
        _write_json(artifact_directory / "result.json", result)
        _write_json(artifact_directory / "classification.json", classification)
        _atomic_write(
            artifact_directory / "authoritative-result.txt",
            f"{technical_failure_label}\n".encode("utf-8"),
        )
        # Result/classification are part of the manifest.  Regenerate after a
        # late preservation finding so the final manifest remains truthful.
        try:
            _preserve(artifact_directory, 1)
            _preserve(artifact_directory, 2)
            manifest_validation = validate_self_excluding_manifest(
                artifact_directory
            )
            _write_json(
                artifact_directory / "manifest-validation.json",
                manifest_validation,
            )
        except BaseException:
            pass

    save_finalizer_state(state_path, state)
    return TotalFinalizationOutcome(
        state=state,
        result=result,
        classification=classification,
        operational_stage_results=operational,
        manifest_validation=manifest_validation,
    )


def validate_total_finalization_artifacts(artifact: Path) -> dict[str, Any]:
    required = {
        "artifact-preservation-idempotency.json",
        "authoritative-result.txt",
        "classification.json",
        "finalizer-operational-stages.json",
        "finalizer-state.json",
        "manifest-validation.json",
        "performance-summary.json",
        "preservation-pass-1.json",
        "preservation-pass-2.json",
        "result.json",
        "sha256-manifest.txt",
    }
    missing = sorted(name for name in required if not (artifact / name).is_file())
    state = load_finalizer_state(artifact / "finalizer-state.json")
    manifest = (
        json.loads((artifact / "manifest-validation.json").read_text())
        if not missing and (artifact / "manifest-validation.json").is_file()
        else {"pass": False}
    )
    idempotency = (
        json.loads(
            (artifact / "artifact-preservation-idempotency.json").read_text()
        )
        if (artifact / "artifact-preservation-idempotency.json").is_file()
        else {"pass": False}
    )
    all_attempted = all(
        status != "pending" for status in state.stage_statuses.values()
    )
    return {
        "schema": "qwen32b-calculator-finalization-validation-v1",
        "missing": missing,
        "all_stages_attempted": all_attempted,
        "manifest_valid": manifest.get("pass") is True,
        "preservation_idempotent": idempotency.get("pass") is True,
        "authoritative_result_generated": (
            artifact / "authoritative-result.txt"
        ).is_file(),
        "pass": (
            not missing
            and all_attempted
            and manifest.get("pass") is True
            and idempotency.get("pass") is True
            and state.final_exit_chosen_after_all_stages
        ),
    }
