#!/usr/bin/env python3
"""Preflight or execute one immutable run through the shared final runner."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.experiment_models import (  # noqa: E402
    ModelProfileError,
    get_model_profile,
)
from cmpilot.final_experiment import (  # noqa: E402
    FinalExperimentError,
    reserve_run_attempt,
    resolve_final_run_context,
)
from cmpilot.final_runner import (  # noqa: E402
    FinalRunRequest,
    FinalRunnerError,
    run_final_run,
)
from cmpilot.final_runtime_backends import (  # noqa: E402
    MODEL_EXECUTORS,
    SCIENTIFIC_BACKENDS,
)
from cmpilot.final_submission import (  # noqa: E402
    FinalSubmissionError,
    load_frozen_submission_inputs,
)


PREFLIGHT_SCHEMA = "cmpilot-final-run-preflight-v1"
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--expected-matrix-sha256", required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument(
        "--allow-synthetic-diagnostic",
        action="store_true",
        help="allow an explicitly labelled synthetic manifest only for preflight tests",
    )
    return parser


def _safe_identifier(value: str, *, name: str) -> bool:
    return bool(value and _IDENTIFIER.fullmatch(value))


def _runtime_backend_id(family: Mapping[str, Any]) -> str | None:
    task = family.get("task_specification")
    if not isinstance(task, Mapping):
        return None
    value = task.get("runtime_backend_id")
    return value if isinstance(value, str) and value else None


def _model_profile_check(context: Mapping[str, Any]) -> tuple[bool, str]:
    key = str(context["model_profile_key"])
    manifest_record = context["model_profile"]
    if not isinstance(manifest_record, Mapping):
        return False, "manifest model profile is not an object"
    try:
        profile = get_model_profile(key)
        expected = profile.final_experiment_record(
            step_limit=int(manifest_record["step_limit"])
        )
        if expected != manifest_record:
            return False, "manifest model profile differs from checked-in profile"
        profile.verify_static_inputs(ROOT)
    except (KeyError, OSError, TypeError, ValueError, ModelProfileError) as error:
        return False, f"{type(error).__name__}: {error}"
    if key not in MODEL_EXECUTORS:
        return False, f"no checked-in model executor is registered for {key}"
    try:
        executor = MODEL_EXECUTORS[key](context)
    except Exception as error:
        return False, f"model executor preflight failed: {type(error).__name__}: {error}"
    if not callable(getattr(executor, "execute_agent", None)) or not callable(
        getattr(executor, "shutdown", None)
    ):
        return False, "registered model executor does not satisfy the shared interface"
    return True, "checked-in model profile and executor verified"


def build_preflight(
    *,
    manifest_path: Path,
    expected_manifest_sha256: str,
    matrix_path: Path,
    expected_matrix_sha256: str,
    run_root: Path,
    run_id: str,
    job_id: str,
    attempt_id: str,
    allow_synthetic: bool = False,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Return readiness evidence without creating run-root state."""

    checks: dict[str, bool] = {
        "attempt_identity": False,
        "family_backend": False,
        "frozen_inputs": False,
        "model_profile_and_executor": False,
        "run_identity": False,
        "run_root_unchanged": True,
    }
    diagnostics: dict[str, str] = {}
    context: dict[str, Any] | None = None
    run_root_existed = run_root.exists() or run_root.is_symlink()
    try:
        manifest, matrix, manifest_sha256, matrix_sha256 = (
            load_frozen_submission_inputs(
                manifest_path,
                matrix_path,
                expected_manifest_sha256=expected_manifest_sha256,
                expected_matrix_sha256=expected_matrix_sha256,
                allow_synthetic=allow_synthetic,
            )
        )
        checks["frozen_inputs"] = True
        matches = [run for run in matrix["runs"] if run.get("run_id") == run_id]
        if len(matches) != 1:
            diagnostics["run_identity"] = (
                f"run ID must occur exactly once in the matrix: {run_id}"
            )
        else:
            context = resolve_final_run_context(
                manifest, matches[0], allow_synthetic=allow_synthetic
            )
            checks["run_identity"] = True
            diagnostics["run_identity"] = "exact manifest/matrix run resolved"

        attempt_valid = (
            _safe_identifier(job_id, name="job_id")
            and _safe_identifier(attempt_id, name="attempt_id")
            and (
                attempt_id == f"slurm-{job_id}"
                or attempt_id.startswith(f"slurm-{job_id}-")
                or (job_id == "PRE_SUBMISSION" and attempt_id == "PRE_SUBMISSION")
            )
        )
        checks["attempt_identity"] = attempt_valid
        diagnostics["attempt_identity"] = (
            "job/attempt provenance is well formed"
            if attempt_valid
            else "attempt ID must be PRE_SUBMISSION or derive from the Slurm job ID"
        )

        if context is not None:
            model_ready, model_diagnostic = _model_profile_check(context)
            checks["model_profile_and_executor"] = model_ready
            diagnostics["model_profile_and_executor"] = model_diagnostic
            backend_id = _runtime_backend_id(context["family_manifest"])
            backend_ready = backend_id is not None and backend_id in SCIENTIFIC_BACKENDS
            checks["family_backend"] = backend_ready
            diagnostics["family_backend"] = (
                f"checked-in scientific backend verified: {backend_id}"
                if backend_ready
                else (
                    "family task specification has no registered runtime backend; "
                    "waiting for the final TPTM-selected family package"
                )
            )
    except (OSError, FinalExperimentError, FinalSubmissionError) as error:
        diagnostics["frozen_inputs"] = f"{type(error).__name__}: {error}"
        manifest_sha256 = expected_manifest_sha256
        matrix_sha256 = expected_matrix_sha256

    run_root_changed = (run_root.exists() or run_root.is_symlink()) != run_root_existed
    checks["run_root_unchanged"] = not run_root_changed
    overall = "PASS" if all(checks.values()) else "FAIL"
    record = {
        "attempt_id": attempt_id,
        "checks": checks,
        "diagnostics": diagnostics,
        "experiment_manifest_sha256": manifest_sha256,
        "job_id": job_id,
        "matrix_sha256": matrix_sha256,
        "model_profile": (
            None if context is None else context["model_profile_key"]
        ),
        "overall": overall,
        "run_id": run_id,
        "schema": PREFLIGHT_SCHEMA,
        "side_effects": False,
    }
    return record, context


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.allow_synthetic_diagnostic and not arguments.preflight_only:
        raise FinalRunnerError(
            "synthetic diagnostics are permitted only with --preflight-only"
        )
    record, context = build_preflight(
        manifest_path=arguments.manifest,
        expected_manifest_sha256=arguments.expected_manifest_sha256,
        matrix_path=arguments.matrix,
        expected_matrix_sha256=arguments.expected_matrix_sha256,
        run_root=arguments.run_root,
        run_id=arguments.run_id,
        job_id=arguments.job_id,
        attempt_id=arguments.attempt_id,
        allow_synthetic=arguments.allow_synthetic_diagnostic,
    )
    if arguments.preflight_only or record["overall"] != "PASS":
        print(json.dumps(record, ensure_ascii=False, sort_keys=True))
        return 0 if record["overall"] == "PASS" else 1

    if context is None:  # pragma: no cover - guarded by PASS
        raise FinalRunnerError("run context disappeared after successful preflight")
    run = context["run"]
    attempt = reserve_run_attempt(
        run,
        arguments.run_root,
        slurm_job_id=arguments.job_id,
        attempt_id=arguments.attempt_id,
    )
    backend_id = _runtime_backend_id(context["family_manifest"])
    if backend_id is None:  # pragma: no cover - guarded by PASS
        raise FinalRunnerError("family backend disappeared after preflight")
    scientific = SCIENTIFIC_BACKENDS[backend_id](context)
    model = MODEL_EXECUTORS[str(context["model_profile_key"])](context)
    request = FinalRunRequest(
        family=context["family_manifest"],
        condition=str(context["condition"]),
        model_profile_key=str(context["model_profile_key"]),
        model_profile=context["model_profile"],
        seed=int(context["seed"]),
        run=run,
        attempt_directory=attempt,
        job_id=arguments.job_id,
        attempt_id=arguments.attempt_id,
    )
    outcome = run_final_run(request, scientific=scientific, model=model)
    terminal = {
        "attempt_directory": str(attempt),
        "final_exit_code": outcome.state.final_exit_code,
        "run_id": request.run_id,
        "schema": "cmpilot-final-run-worker-result-v1",
        "terminal": outcome.state.final_exit_chosen_after_all_stages,
    }
    print(json.dumps(terminal, ensure_ascii=False, sort_keys=True))
    return int(outcome.state.final_exit_code or 0)


if __name__ == "__main__":
    raise SystemExit(main())
