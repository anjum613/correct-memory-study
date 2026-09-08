"""Fail-closed Slurm planning for the frozen final experiment.

One array element owns one immutable atomic run.  Arrays are model-profile
specific, so Qwen can be scheduled independently of Devstral, while every
element keeps the cluster's validated single-node, two-A100 resource shape.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any

from .batch_script_attestation import (
    ATTESTATION_PASS,
    attest_batch_script_files,
    retrieve_controller_batch_script,
)
from .final_experiment import (
    FROZEN,
    PRODUCTION,
    FinalExperimentError,
    build_run_matrix,
    canonical_json_bytes,
    classify_run_attempts,
    load_experiment_manifest,
    load_run_matrix,
    sha256_bytes,
    validate_run_matrix,
    write_new_canonical_json,
)


SUBMISSION_PLAN_SCHEMA = "cmpilot-final-slurm-submission-plan-v1"
SUBMISSION_PREVIEW_SCHEMA = "cmpilot-final-slurm-submission-preview-v1"
SUBMISSION_RESULT_SCHEMA = "cmpilot-final-slurm-submission-result-v1"
RUNNER_PREFLIGHT_SCHEMA = "cmpilot-final-run-preflight-v1"
RUNNER_PREFLIGHT_SUMMARY_SCHEMA = "cmpilot-final-run-preflight-summary-v1"
MAX_ARRAY_SIZE = 1001
RESOURCES = {
    "a100_gpus": 2,
    "cpus_per_task": 8,
    "memory": "128G",
    "nodes": 1,
    "partition": "gpu",
    "tasks": 1,
    "walltime": "00:45:00",
}

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_JOB_ID = re.compile(r"^[0-9]+$")


class FinalSubmissionError(FinalExperimentError):
    """A final production submission is not frozen, unique, or schedulable."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise FinalSubmissionError(f"cannot hash submission input {path}: {error}") from error
    return digest.hexdigest()


def _require_sha256(value: Any, *, name: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise FinalSubmissionError(f"{name} must be an exact lowercase SHA-256")
    return value


def _positive_int(value: Any, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise FinalSubmissionError(f"{name} must be a positive integer")
    return value


def _absolute_path(path: Path, *, name: str) -> Path:
    value = Path(path).absolute()
    if value == Path("/"):
        raise FinalSubmissionError(f"{name} must not be the filesystem root")
    return value


def load_frozen_submission_inputs(
    manifest_path: Path,
    matrix_path: Path,
    *,
    expected_manifest_sha256: str,
    expected_matrix_sha256: str,
    allow_synthetic: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], str, str]:
    """Load and cross-check the exact canonical six-family freeze and matrix."""

    manifest, manifest_sha256 = load_experiment_manifest(
        manifest_path,
        expected_sha256=_require_sha256(
            expected_manifest_sha256, name="expected_manifest_sha256"
        ),
        allow_synthetic=allow_synthetic,
    )
    matrix, matrix_sha256 = load_run_matrix(
        matrix_path,
        expected_sha256=_require_sha256(
            expected_matrix_sha256, name="expected_matrix_sha256"
        ),
    )
    if matrix["experiment_manifest_sha256"] != manifest_sha256:
        raise FinalSubmissionError(
            "run matrix does not name the exact frozen experiment manifest"
        )
    rebuilt = build_run_matrix(
        manifest,
        experiment_manifest_sha256=manifest_sha256,
        allow_synthetic=allow_synthetic,
    )
    if rebuilt != matrix:
        raise FinalSubmissionError(
            "run matrix is not the deterministic matrix of the supplied frozen manifest"
        )
    return manifest, matrix, manifest_sha256, matrix_sha256


def build_submission_plan(
    matrix: Any,
    output_root: Path,
    *,
    matrix_sha256: str,
    model_profile: str,
    concurrency: int,
    allow_synthetic: bool = False,
) -> dict[str, Any]:
    """Select restartable runs for one model-specific Slurm array."""

    matrix = validate_run_matrix(matrix)
    if not allow_synthetic and (
        matrix.get("purpose") != PRODUCTION or matrix.get("freeze_status") != FROZEN
    ):
        raise FinalSubmissionError(
            "production submission planning requires a PRODUCTION/FROZEN manifest"
        )
    matrix_sha256 = _require_sha256(matrix_sha256, name="matrix_sha256")
    concurrency = _positive_int(concurrency, name="concurrency")
    if concurrency >= MAX_ARRAY_SIZE:
        raise FinalSubmissionError(
            f"concurrency must be below the cluster MaxArraySize {MAX_ARRAY_SIZE}"
        )
    if not isinstance(model_profile, str) or not model_profile:
        raise FinalSubmissionError("model_profile must be a non-empty string")
    available = matrix.get("dimensions", {}).get("models", [])
    if model_profile not in available:
        raise FinalSubmissionError(
            f"model profile is absent from the frozen matrix: {model_profile!r}"
        )
    output_root = _absolute_path(Path(output_root), name="output_root")
    if output_root.is_symlink():
        raise FinalSubmissionError(f"output_root must not be a symlink: {output_root}")
    if output_root.exists() and not output_root.is_dir():
        raise FinalSubmissionError(f"output_root is not a directory: {output_root}")

    eligible: list[dict[str, Any]] = []
    completed: list[dict[str, Any]] = []
    profile_runs = [
        run for run in matrix["runs"] if run["model_profile"] == model_profile
    ]
    for run in profile_runs:
        inventory = classify_run_attempts(run, output_root)
        if inventory["state"] == "COMPLETED":
            completed.append(
                {
                    "completed_attempt": inventory["completed_attempt"],
                    "run_id": run["run_id"],
                }
            )
            continue
        eligible.append(
            {
                "array_index": len(eligible),
                "attempt_mode": (
                    "NEW_IMMUTABLE_ATTEMPT"
                    if inventory["requires_new_attempt"]
                    else "INITIAL_IMMUTABLE_ATTEMPT"
                ),
                "prior_state": inventory["state"],
                "run_id": run["run_id"],
            }
        )

    if len(eligible) >= MAX_ARRAY_SIZE:
        raise FinalSubmissionError(
            f"eligible array size {len(eligible)} exceeds cluster limit "
            f"{MAX_ARRAY_SIZE - 1}"
        )
    array_specification = (
        None if not eligible else f"0-{len(eligible) - 1}%{concurrency}"
    )
    return validate_submission_plan(
        {
            "schema": SUBMISSION_PLAN_SCHEMA,
            "purpose": matrix["purpose"],
            "freeze_status": matrix["freeze_status"],
            "protocol_version": matrix["protocol_version"],
            "experiment_manifest_sha256": matrix[
                "experiment_manifest_sha256"
            ],
            "matrix_sha256": matrix_sha256,
            "run_ids_sha256": matrix["run_ids_sha256"],
            "model_profile": model_profile,
            "output_root": str(output_root),
            "resources": RESOURCES,
            "concurrency": concurrency,
            "array_specification": array_specification,
            "profile_run_count": len(profile_runs),
            "eligible_run_count": len(eligible),
            "completed_run_count": len(completed),
            "eligible_runs": eligible,
            "excluded_completed_runs": completed,
        }
    )


def validate_submission_plan(value: Any) -> dict[str, Any]:
    """Validate an independently persisted immutable submission plan."""

    if not isinstance(value, Mapping):
        raise FinalSubmissionError("submission plan must be a JSON object")
    if value.get("schema") != SUBMISSION_PLAN_SCHEMA:
        raise FinalSubmissionError(
            f"unsupported submission plan schema: {value.get('schema')!r}"
        )
    purpose = value.get("purpose")
    freeze_status = value.get("freeze_status")
    if purpose not in {"PRODUCTION", "SYNTHETIC_UNIT_TEST"}:
        raise FinalSubmissionError("submission plan has an invalid manifest purpose")
    if (purpose == "PRODUCTION" and freeze_status != "FROZEN") or (
        purpose == "SYNTHETIC_UNIT_TEST" and freeze_status != "SYNTHETIC_ONLY"
    ):
        raise FinalSubmissionError("submission plan has an invalid freeze status")
    _require_sha256(
        value.get("experiment_manifest_sha256"),
        name="experiment_manifest_sha256",
    )
    _require_sha256(value.get("matrix_sha256"), name="matrix_sha256")
    _require_sha256(value.get("run_ids_sha256"), name="run_ids_sha256")
    if not isinstance(value.get("protocol_version"), str) or not value[
        "protocol_version"
    ]:
        raise FinalSubmissionError("protocol_version must not be empty")
    profile = value.get("model_profile")
    if not isinstance(profile, str) or not profile:
        raise FinalSubmissionError("model_profile must not be empty")
    output_root = Path(str(value.get("output_root", "")))
    if not output_root.is_absolute() or output_root == Path("/"):
        raise FinalSubmissionError("submission output_root must be absolute and narrow")
    concurrency = _positive_int(value.get("concurrency"), name="concurrency")
    if concurrency >= MAX_ARRAY_SIZE:
        raise FinalSubmissionError("submission concurrency exceeds cluster limits")
    if value.get("resources") != RESOURCES:
        raise FinalSubmissionError(
            "submission resources must be one node with exactly two A100 GPUs"
        )
    eligible = value.get("eligible_runs")
    completed = value.get("excluded_completed_runs")
    if not isinstance(eligible, list) or not isinstance(completed, list):
        raise FinalSubmissionError("submission run inventories must be lists")
    if value.get("eligible_run_count") != len(eligible):
        raise FinalSubmissionError("eligible_run_count does not match its inventory")
    if value.get("completed_run_count") != len(completed):
        raise FinalSubmissionError("completed_run_count does not match its inventory")
    if value.get("profile_run_count") != len(eligible) + len(completed):
        raise FinalSubmissionError("profile_run_count does not match run inventories")

    eligible_ids: list[str] = []
    for index, row in enumerate(eligible):
        if not isinstance(row, Mapping):
            raise FinalSubmissionError(f"eligible_runs[{index}] must be an object")
        if row.get("array_index") != index:
            raise FinalSubmissionError("eligible array indices must be contiguous")
        if row.get("prior_state") not in {"ABSENT", "INTERRUPTED"}:
            raise FinalSubmissionError("eligible run has an invalid prior state")
        expected_mode = (
            "NEW_IMMUTABLE_ATTEMPT"
            if row.get("prior_state") == "INTERRUPTED"
            else "INITIAL_IMMUTABLE_ATTEMPT"
        )
        if row.get("attempt_mode") != expected_mode:
            raise FinalSubmissionError("eligible run has an invalid attempt mode")
        run_id = row.get("run_id")
        if not isinstance(run_id, str) or not run_id.startswith("run-"):
            raise FinalSubmissionError("eligible run has an invalid run ID")
        eligible_ids.append(run_id)
    completed_ids: list[str] = []
    for index, row in enumerate(completed):
        if not isinstance(row, Mapping):
            raise FinalSubmissionError(
                f"excluded_completed_runs[{index}] must be an object"
            )
        run_id = row.get("run_id")
        attempt = row.get("completed_attempt")
        if not isinstance(run_id, str) or not run_id.startswith("run-"):
            raise FinalSubmissionError("completed run has an invalid run ID")
        if not isinstance(attempt, str) or not attempt:
            raise FinalSubmissionError("completed run has no completed attempt")
        completed_ids.append(run_id)
    all_ids = eligible_ids + completed_ids
    if len(set(all_ids)) != len(all_ids):
        raise FinalSubmissionError("submission plan contains duplicate atomic run IDs")
    expected_array = None if not eligible else f"0-{len(eligible) - 1}%{concurrency}"
    if value.get("array_specification") != expected_array:
        raise FinalSubmissionError("array specification does not match eligible runs")
    try:
        return json.loads(canonical_json_bytes(value))
    except (TypeError, ValueError) as error:
        raise FinalSubmissionError(f"submission plan is not pure JSON: {error}") from error


def submission_plan_sha256(plan: Any) -> str:
    return sha256_bytes(canonical_json_bytes(validate_submission_plan(plan)))


def load_submission_plan(
    path: Path,
    *,
    expected_sha256: str,
) -> tuple[dict[str, Any], str]:
    """Load an exact canonical plan without accepting a floating file."""

    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise FinalSubmissionError(f"submission plan is not a regular file: {path}")
    payload = path.read_bytes()
    actual = sha256_bytes(payload)
    expected = _require_sha256(expected_sha256, name="expected plan SHA-256")
    if actual != expected:
        raise FinalSubmissionError(
            f"submission plan hash mismatch: expected={expected}, actual={actual}"
        )
    try:
        raw = json.loads(payload.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise FinalSubmissionError(f"invalid submission plan JSON: {path}: {error}") from error
    if payload != canonical_json_bytes(raw):
        raise FinalSubmissionError(f"submission plan is not canonical JSON: {path}")
    return validate_submission_plan(raw), actual


def select_run_id(
    plan: Any,
    *,
    model_profile: str,
    array_index: int,
) -> str:
    """Resolve exactly one run ID for a model-specific Slurm array element."""

    plan = validate_submission_plan(plan)
    if plan["model_profile"] != model_profile:
        raise FinalSubmissionError("array requested a different model profile")
    if isinstance(array_index, bool) or not isinstance(array_index, int):
        raise FinalSubmissionError("array_index must be an integer")
    if array_index < 0 or array_index >= len(plan["eligible_runs"]):
        raise FinalSubmissionError(f"array_index is outside the frozen plan: {array_index}")
    row = plan["eligible_runs"][array_index]
    if row["array_index"] != array_index:  # pragma: no cover - plan validation guards it
        raise FinalSubmissionError("array index changed in the frozen plan")
    return str(row["run_id"])


def _job_name(plan: Mapping[str, Any]) -> str:
    profile = re.sub(r"[^a-z0-9]+", "-", str(plan["model_profile"]).lower()).strip("-")
    if not profile:
        profile = "model"
    return f"cmpf-{profile[:32]}-{str(plan['matrix_sha256'])[:10]}"


def render_sbatch_command(
    plan: Any,
    *,
    batch_script: Path,
    project_root: Path,
    controller_python: Path,
    manifest_path: Path,
    manifest_sha256: str,
    matrix_path: Path,
    plan_path: Path,
    plan_sha256: str,
    runner_script: Path,
    log_root: Path,
    begin: str,
    sbatch: Path = Path("/slurm/bin/sbatch"),
) -> tuple[str, ...] | None:
    """Render the exact argv used by the production submission path."""

    plan = validate_submission_plan(plan)
    if not plan["eligible_runs"]:
        return None
    manifest_sha256 = _require_sha256(
        manifest_sha256, name="manifest_sha256"
    )
    if manifest_sha256 != plan["experiment_manifest_sha256"]:
        raise FinalSubmissionError("manifest_sha256 does not match submission plan")
    plan_sha256 = _require_sha256(plan_sha256, name="plan_sha256")
    if plan_sha256 != submission_plan_sha256(plan):
        raise FinalSubmissionError("plan_sha256 does not match submission plan")
    paths = {
        "batch_script": _absolute_path(batch_script, name="batch_script"),
        "controller_python": _absolute_path(
            controller_python, name="controller_python"
        ),
        "log_root": _absolute_path(log_root, name="log_root"),
        "manifest_path": _absolute_path(manifest_path, name="manifest_path"),
        "matrix_path": _absolute_path(matrix_path, name="matrix_path"),
        "plan_path": _absolute_path(plan_path, name="plan_path"),
        "project_root": _absolute_path(project_root, name="project_root"),
        "runner_script": _absolute_path(runner_script, name="runner_script"),
    }
    job_name = _job_name(plan)
    return (
        str(Path(sbatch)),
        "--parsable",
        "--export=NONE",
        f"--begin={begin}",
        f"--array={plan['array_specification']}",
        f"--job-name={job_name}",
        f"--output={paths['log_root'] / (job_name + '-%A_%a.out')}",
        f"--error={paths['log_root'] / (job_name + '-%A_%a.err')}",
        str(paths["batch_script"]),
        str(paths["project_root"]),
        str(paths["controller_python"]),
        str(paths["runner_script"]),
        str(paths["manifest_path"]),
        manifest_sha256,
        str(paths["matrix_path"]),
        str(plan["matrix_sha256"]),
        str(paths["plan_path"]),
        plan_sha256,
        str(Path(plan["output_root"])),
        str(plan["model_profile"]),
    )


def render_runner_preflight_commands(
    plan: Any,
    *,
    controller_python: Path,
    runner_script: Path,
    manifest_path: Path,
    manifest_sha256: str,
    matrix_path: Path,
) -> tuple[tuple[str, ...], ...]:
    """Render one side-effect-free shared-runner gate for every eligible run."""

    plan = validate_submission_plan(plan)
    manifest_sha256 = _require_sha256(
        manifest_sha256, name="manifest_sha256"
    )
    if manifest_sha256 != plan["experiment_manifest_sha256"]:
        raise FinalSubmissionError("manifest_sha256 does not match submission plan")
    paths = {
        "controller_python": _absolute_path(
            controller_python, name="controller_python"
        ),
        "manifest_path": _absolute_path(manifest_path, name="manifest_path"),
        "matrix_path": _absolute_path(matrix_path, name="matrix_path"),
        "runner_script": _absolute_path(runner_script, name="runner_script"),
    }
    return tuple(
        (
            str(paths["controller_python"]),
            str(paths["runner_script"]),
            "--manifest",
            str(paths["manifest_path"]),
            "--expected-manifest-sha256",
            manifest_sha256,
            "--matrix",
            str(paths["matrix_path"]),
            "--expected-matrix-sha256",
            str(plan["matrix_sha256"]),
            "--run-root",
            str(plan["output_root"]),
            "--run-id",
            str(row["run_id"]),
            "--job-id",
            "PRE_SUBMISSION",
            "--attempt-id",
            "PRE_SUBMISSION",
            "--preflight-only",
        )
        for row in plan["eligible_runs"]
    )


def build_submission_preview(
    plan: Any,
    *,
    command: Sequence[str] | None,
    batch_script: Path,
    plan_path: Path,
    manifest_path: Path,
    matrix_path: Path,
    runner_preflight_commands: Sequence[Sequence[str]] = (),
) -> dict[str, Any]:
    """Return a complete dry-run record; callers need not write any file."""

    plan = validate_submission_plan(plan)
    plan_sha256 = submission_plan_sha256(plan)
    return {
        "schema": SUBMISSION_PREVIEW_SCHEMA,
        "dry_run": True,
        "production_submitted": False,
        "batch_script": {
            "path": str(_absolute_path(batch_script, name="batch_script")),
            "sha256": sha256_file(batch_script),
        },
        "manifest_path": str(_absolute_path(manifest_path, name="manifest_path")),
        "matrix_path": str(_absolute_path(matrix_path, name="matrix_path")),
        "plan": plan,
        "plan_path": str(_absolute_path(plan_path, name="plan_path")),
        "plan_sha256": plan_sha256,
        "sbatch_argv": None if command is None else list(command),
        "submission_required": command is not None,
        "runner_preflight": {
            "command_count": len(runner_preflight_commands),
            "commands": [list(item) for item in runner_preflight_commands],
            "status": "NOT_RUN",
        },
    }


def _run(
    argv: Sequence[str], *, timeout: int = 60
) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            list(argv),
            check=False,
            capture_output=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise FinalSubmissionError(f"submission command failed: {argv[0]}: {error}") from error


def _write_new_bytes(path: Path, payload: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise FinalSubmissionError(f"refusing to overwrite submission evidence: {path}") from error
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _write_process(directory: Path, name: str, result: subprocess.CompletedProcess[bytes]) -> None:
    _write_new_bytes(directory / f"{name}.stdout", result.stdout)
    _write_new_bytes(directory / f"{name}.stderr", result.stderr)
    write_new_canonical_json(
        directory / f"{name}.json",
        {"argv": list(result.args), "exit_code": result.returncode},
    )


def _parse_job_id(stdout: bytes) -> str | None:
    try:
        candidate = stdout.decode("utf-8").strip().split(";", 1)[0]
    except UnicodeDecodeError:
        return None
    return candidate if _JOB_ID.fullmatch(candidate) else None


def run_runner_preflights(
    plan: Any,
    *,
    commands: Sequence[Sequence[str]],
    evidence_directory: Path,
) -> dict[str, Any]:
    """Execute and preserve every read-only shared-runner compatibility gate."""

    plan = validate_submission_plan(plan)
    if len(commands) != plan["eligible_run_count"]:
        raise FinalSubmissionError(
            "runner preflight command inventory differs from eligible runs"
        )
    evidence_directory = _absolute_path(
        evidence_directory, name="runner preflight evidence"
    )
    try:
        evidence_directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError as error:
        raise FinalSubmissionError(
            f"refusing to overwrite runner preflight evidence: {evidence_directory}"
        ) from error

    rows: list[dict[str, Any]] = []
    for index, (eligible, raw_command) in enumerate(
        zip(plan["eligible_runs"], commands, strict=True)
    ):
        command = tuple(str(item) for item in raw_command)
        try:
            run_id_operand = command[command.index("--run-id") + 1]
            job_id_operand = command[command.index("--job-id") + 1]
            attempt_id_operand = command[command.index("--attempt-id") + 1]
        except (ValueError, IndexError) as error:
            raise FinalSubmissionError(
                f"runner preflight {index} is missing required operands"
            ) from error
        if (
            command[-1:] != ("--preflight-only",)
            or run_id_operand != eligible["run_id"]
            or job_id_operand != "PRE_SUBMISSION"
            or attempt_id_operand != "PRE_SUBMISSION"
        ):
            raise FinalSubmissionError(
                f"runner preflight {index} does not name its exact eligible run"
            )
        try:
            completed = _run(command, timeout=180)
        except FinalSubmissionError as error:
            completed = subprocess.CompletedProcess(
                command,
                127,
                stdout=b"",
                stderr=f"{type(error).__name__}: {error}".encode("utf-8"),
            )
        prefix = f"{index:04d}-{eligible['run_id']}"
        _write_process(evidence_directory, prefix, completed)
        parsed: Mapping[str, Any] | None = None
        parse_error: str | None = None
        try:
            candidate = json.loads(completed.stdout.decode("utf-8"))
            if isinstance(candidate, Mapping):
                parsed = candidate
            else:
                parse_error = "stdout JSON is not an object"
        except (UnicodeError, json.JSONDecodeError) as error:
            parse_error = f"{type(error).__name__}: {error}"
        checks = parsed.get("checks") if parsed is not None else None
        passed = bool(
            completed.returncode == 0
            and parsed is not None
            and parsed.get("schema") == RUNNER_PREFLIGHT_SCHEMA
            and parsed.get("run_id") == eligible["run_id"]
            and parsed.get("model_profile") == plan["model_profile"]
            and isinstance(checks, Mapping)
            and checks
            and all(value is True for value in checks.values())
            and parsed.get("overall") == "PASS"
        )
        row = {
            "array_index": index,
            "exit_code": completed.returncode,
            "parse_error": parse_error,
            "pass": passed,
            "result": None if parsed is None else dict(parsed),
            "run_id": eligible["run_id"],
        }
        write_new_canonical_json(evidence_directory / f"{prefix}.result.json", row)
        rows.append(row)
    summary = {
        "schema": RUNNER_PREFLIGHT_SUMMARY_SCHEMA,
        "model_profile": plan["model_profile"],
        "pass": len(rows) == plan["eligible_run_count"]
        and all(row["pass"] for row in rows),
        "run_count": len(rows),
        "runs": rows,
    }
    write_new_canonical_json(evidence_directory / "summary.json", summary)
    return summary


def submit_attested_array(
    plan: Any,
    *,
    command: Sequence[str],
    batch_script: Path,
    evidence_directory: Path,
    provenance: Mapping[str, Any] | None = None,
    squeue: Path = Path("/slurm/bin/squeue"),
    scontrol: Path = Path("/slurm/bin/scontrol"),
    scancel: Path = Path("/slurm/bin/scancel"),
) -> dict[str, Any]:
    """Submit one array once and controller-attest the unmodified worker script."""

    plan = validate_submission_plan(plan)
    if not plan["eligible_runs"]:
        raise FinalSubmissionError("submission plan has no eligible runs")
    if plan["purpose"] != PRODUCTION or plan["freeze_status"] != FROZEN:
        raise FinalSubmissionError(
            "live Slurm submission requires a PRODUCTION/FROZEN plan"
        )
    command = tuple(str(item) for item in command)
    if not command or command[0] != "/slurm/bin/sbatch":
        raise FinalSubmissionError("production command must use /slurm/bin/sbatch")
    batch_script = Path(batch_script).resolve(strict=True)
    if len(command) < 9 or Path(command[8]).resolve() != batch_script:
        raise FinalSubmissionError(
            "submission command does not execute the attested array script"
        )
    evidence_directory = _absolute_path(
        evidence_directory, name="evidence_directory"
    )
    try:
        evidence_directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError as error:
        raise FinalSubmissionError(
            f"refusing to overwrite submission evidence: {evidence_directory}"
        ) from error

    job_name_values = [item.split("=", 1)[1] for item in command if item.startswith("--job-name=")]
    if len(job_name_values) != 1:
        raise FinalSubmissionError("submission command must contain one deterministic job name")
    queue = _run(
        (
            str(squeue),
            "-h",
            "-u",
            os.environ.get("USER", "s224049759"),
            "-o",
            "%i|%j|%T",
        )
    )
    _write_process(evidence_directory, "pre-submission-queue", queue)
    if queue.returncode != 0:
        raise FinalSubmissionError("could not inspect active Slurm jobs")
    queue_lines = queue.stdout.decode("utf-8", errors="replace").splitlines()
    active = [
        line
        for line in queue_lines
        if len(line.split("|")) >= 2 and line.split("|")[1] == job_name_values[0]
    ]
    if active:
        raise FinalSubmissionError(
            f"matching final-experiment array is already active: {active}"
        )

    submission = _run(command)
    _write_process(evidence_directory, "submission", submission)
    job_id = _parse_job_id(submission.stdout) if submission.returncode == 0 else None
    record: dict[str, Any] = {
        "schema": SUBMISSION_RESULT_SCHEMA,
        "attestation": None,
        "cancelled": False,
        "job_id": job_id,
        "model_profile": plan["model_profile"],
        "pass": False,
        "plan_sha256": submission_plan_sha256(plan),
        "run_count": plan["eligible_run_count"],
        "submission_argv": list(command),
        "provenance": (
            None
            if provenance is None
            else json.loads(canonical_json_bytes(provenance))
        ),
    }
    if job_id is None:
        record["error"] = "sbatch did not return a valid numeric job ID"
        write_new_canonical_json(evidence_directory / "submission-record.json", record)
        return record

    try:
        controller_path = evidence_directory / "controller-batch-script.sbatch"
        retrieval = retrieve_controller_batch_script(
            job_id,
            controller_path,
            evidence_dir=evidence_directory,
            scontrol=scontrol,
        )
        record["controller_retrieval"] = retrieval
        if retrieval.get("pass"):
            attestation = attest_batch_script_files(
                batch_script,
                controller_path,
                evidence_dir=evidence_directory,
            )
        else:
            attestation = {
                "label": "CONTROLLER_BATCH_SCRIPT_ATTESTATION_FAILURE",
                "pass": False,
                "reason": "controller script retrieval failed",
            }
        record["attestation"] = attestation
        record["pass"] = bool(
            attestation.get("pass") and attestation.get("label") == ATTESTATION_PASS
        )
    except Exception as error:
        record["error"] = f"{type(error).__name__}: {error}"
    if not record["pass"]:
        cancellation = _run((str(scancel), job_id))
        _write_process(evidence_directory, "cancellation", cancellation)
        record["cancelled"] = cancellation.returncode == 0
        record["cancel_exit_code"] = cancellation.returncode
    write_new_canonical_json(evidence_directory / "submission-record.json", record)
    return record


__all__ = [
    "FinalSubmissionError",
    "MAX_ARRAY_SIZE",
    "RESOURCES",
    "RUNNER_PREFLIGHT_SCHEMA",
    "RUNNER_PREFLIGHT_SUMMARY_SCHEMA",
    "SUBMISSION_PLAN_SCHEMA",
    "SUBMISSION_PREVIEW_SCHEMA",
    "SUBMISSION_RESULT_SCHEMA",
    "build_submission_plan",
    "build_submission_preview",
    "load_frozen_submission_inputs",
    "load_submission_plan",
    "render_sbatch_command",
    "render_runner_preflight_commands",
    "run_runner_preflights",
    "select_run_id",
    "sha256_file",
    "submission_plan_sha256",
    "submit_attested_array",
    "validate_submission_plan",
]
