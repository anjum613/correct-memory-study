#!/usr/bin/env python3
"""Dry-run, submit, or resolve one frozen final-experiment Slurm array."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.final_experiment import (  # noqa: E402
    FinalExperimentError,
    write_new_canonical_json,
)
from cmpilot.final_submission import (  # noqa: E402
    build_submission_plan,
    build_submission_preview,
    load_frozen_submission_inputs,
    load_submission_plan,
    render_sbatch_command,
    render_runner_preflight_commands,
    run_runner_preflights,
    select_run_id,
    submission_plan_sha256,
    submit_attested_array,
)


DEFAULT_BATCH = ROOT / "slurm/final_experiment_array.sbatch"
DEFAULT_RUNNER = ROOT / "scripts/run_final_experiment.py"
DEFAULT_CONTROLLER_PYTHON = Path(
    "/home/s224049759/environments/cmpilot-conda/bin/python"
)
DEFAULT_LOG_ROOT = Path("/home/s224049759/slurm-logs/final-experiment")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    submit = commands.add_parser(
        "submit", description="validate and render or submit one model-profile array"
    )
    submit.add_argument("manifest", type=Path)
    submit.add_argument("matrix", type=Path)
    submit.add_argument("run_root", type=Path)
    submit.add_argument("plan_output", type=Path)
    submit.add_argument("--expected-manifest-sha256", required=True)
    submit.add_argument("--expected-matrix-sha256", required=True)
    submit.add_argument("--model-profile", required=True)
    submit.add_argument("--concurrency", type=int, default=1)
    submit.add_argument("--batch-script", type=Path, default=DEFAULT_BATCH)
    submit.add_argument(
        "--controller-python", type=Path, default=DEFAULT_CONTROLLER_PYTHON
    )
    submit.add_argument("--runner-script", type=Path, default=DEFAULT_RUNNER)
    submit.add_argument("--log-root", type=Path, default=DEFAULT_LOG_ROOT)
    submit.add_argument("--evidence-directory", type=Path)
    submit.add_argument("--begin", default="now+2minutes")
    submit.add_argument("--dry-run", action="store_true")
    submit.add_argument(
        "--allow-synthetic-diagnostic",
        action="store_true",
        help="allow a synthetic fixture only for a non-submitting dry-run",
    )

    select = commands.add_parser(
        "select-run", description="resolve one immutable run ID for an array element"
    )
    select.add_argument("plan", type=Path)
    select.add_argument("--expected-plan-sha256", required=True)
    select.add_argument("--model-profile", required=True)
    select.add_argument("--array-index", required=True, type=int)
    return parser


def _git(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", "-C", str(ROOT), *arguments),
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _require_file(path: Path, *, name: str, executable: bool = False) -> Path:
    try:
        value = Path(path).resolve(strict=True)
    except OSError as error:
        raise FinalExperimentError(f"{name} is unavailable: {path}: {error}") from error
    if not value.is_file():
        raise FinalExperimentError(f"{name} is not a regular file: {value}")
    if executable and not os.access(value, os.X_OK):
        raise FinalExperimentError(f"{name} is not executable: {value}")
    return value


def _select(arguments: argparse.Namespace) -> int:
    plan, _ = load_submission_plan(
        arguments.plan,
        expected_sha256=arguments.expected_plan_sha256,
    )
    print(
        select_run_id(
            plan,
            model_profile=arguments.model_profile,
            array_index=arguments.array_index,
        )
    )
    return 0


def _submit(arguments: argparse.Namespace) -> int:
    if arguments.allow_synthetic_diagnostic and not arguments.dry_run:
        raise FinalExperimentError(
            "synthetic diagnostics are permitted only with --dry-run"
        )
    manifest_path = _require_file(arguments.manifest, name="frozen manifest")
    matrix_path = _require_file(arguments.matrix, name="frozen run matrix")
    batch_script = _require_file(arguments.batch_script, name="array batch script")
    controller_python = _require_file(
        arguments.controller_python,
        name="controller Python",
        executable=True,
    )
    runner_script = _require_file(
        arguments.runner_script, name="shared final runner"
    )
    if not arguments.dry_run and runner_script != DEFAULT_RUNNER.resolve(strict=True):
        raise FinalExperimentError(
            "production submission must use scripts/run_final_experiment.py"
        )
    manifest, matrix, manifest_sha256, matrix_sha256 = load_frozen_submission_inputs(
        manifest_path,
        matrix_path,
        expected_manifest_sha256=arguments.expected_manifest_sha256,
        expected_matrix_sha256=arguments.expected_matrix_sha256,
        allow_synthetic=arguments.allow_synthetic_diagnostic,
    )
    del manifest  # Validation and deterministic matrix reconstruction happened above.
    plan = build_submission_plan(
        matrix,
        arguments.run_root,
        matrix_sha256=matrix_sha256,
        model_profile=arguments.model_profile,
        concurrency=arguments.concurrency,
        allow_synthetic=arguments.allow_synthetic_diagnostic,
    )
    if plan["experiment_manifest_sha256"] != manifest_sha256:  # defensive cross-check
        raise FinalExperimentError("submission plan names a different manifest")

    plan_path = Path(arguments.plan_output).absolute()
    evidence = (
        Path(arguments.evidence_directory).absolute()
        if arguments.evidence_directory is not None
        else Path(str(plan_path) + ".submission-evidence")
    )
    log_root = Path(arguments.log_root).absolute()
    for path, name in ((plan_path, "plan output"), (evidence, "submission evidence")):
        if path.exists() or path.is_symlink():
            raise FinalExperimentError(f"refusing to overwrite {name}: {path}")
    if log_root.is_symlink() or (log_root.exists() and not log_root.is_dir()):
        raise FinalExperimentError(f"log root is not a safe directory: {log_root}")

    plan_sha256 = submission_plan_sha256(plan)
    command = render_sbatch_command(
        plan,
        batch_script=batch_script,
        project_root=ROOT,
        controller_python=controller_python,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha256,
        matrix_path=matrix_path,
        plan_path=plan_path,
        plan_sha256=plan_sha256,
        runner_script=runner_script,
        log_root=log_root,
        begin=arguments.begin,
    )
    preflight_commands = render_runner_preflight_commands(
        plan,
        controller_python=controller_python,
        runner_script=runner_script,
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha256,
        matrix_path=matrix_path,
    )
    preview = build_submission_preview(
        plan,
        command=command,
        batch_script=batch_script,
        plan_path=plan_path,
        manifest_path=manifest_path,
        matrix_path=matrix_path,
        runner_preflight_commands=preflight_commands,
    )
    preview["evidence_directory"] = str(evidence)
    preview["shared_runner"] = {
        "path": str(runner_script),
        "sha256": hashlib.sha256(runner_script.read_bytes()).hexdigest(),
    }

    status = _git("status", "--porcelain")
    commit = _git("rev-parse", "HEAD")
    preview["project_commit"] = (
        commit.stdout.strip() if commit.returncode == 0 else None
    )
    preview["project_worktree_clean"] = status.returncode == 0 and not status.stdout

    if arguments.dry_run or command is None:
        print(json.dumps(preview, ensure_ascii=False, sort_keys=True))
        return 0

    if status.returncode != 0 or status.stdout:
        raise FinalExperimentError(
            "production submission requires a clean committed project worktree"
        )
    if commit.returncode != 0:
        raise FinalExperimentError(f"cannot identify project commit: {commit.stderr}")
    preflight = run_runner_preflights(
        plan,
        commands=preflight_commands,
        evidence_directory=evidence / "runner-preflight",
    )
    if preflight.get("pass") is not True:
        raise FinalExperimentError(
            "shared final runner preflight did not pass for every eligible run"
        )
    log_root.mkdir(parents=True, exist_ok=True)
    written_sha256 = write_new_canonical_json(plan_path, plan)
    if written_sha256 != plan_sha256:  # pragma: no cover - same canonical serializer
        raise FinalExperimentError("persisted submission plan hash changed")
    result = submit_attested_array(
        plan,
        command=command,
        batch_script=batch_script,
        evidence_directory=evidence / "slurm-submission",
        provenance={
            "batch_script_sha256": preview["batch_script"]["sha256"],
            "experiment_manifest_path": str(manifest_path),
            "experiment_manifest_sha256": manifest_sha256,
            "matrix_path": str(matrix_path),
            "matrix_sha256": matrix_sha256,
            "plan_path": str(plan_path),
            "project_commit": commit.stdout.strip(),
            "runner_path": str(runner_script),
            "runner_sha256": preview["shared_runner"]["sha256"],
            "runner_preflight_summary": str(
                evidence / "runner-preflight/summary.json"
            ),
        },
    )
    result.update(
        {
            "experiment_manifest_sha256": manifest_sha256,
            "matrix_sha256": matrix_sha256,
            "plan_path": str(plan_path),
            "project_commit": commit.stdout.strip(),
        }
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("pass") else 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "select-run":
            return _select(arguments)
        return _submit(arguments)
    except (OSError, FinalExperimentError, subprocess.SubprocessError) as error:
        parser.error(str(error))
    return 2  # pragma: no cover - argparse.error exits


if __name__ == "__main__":
    raise SystemExit(main())
