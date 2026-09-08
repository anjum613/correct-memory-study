#!/usr/bin/env python3
"""CPU-only validation of total calculator finalization after job 25692."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import traceback
from typing import Any, Sequence


PASS_LABEL = "FINALIZER_CPU_GATE_PASS"
FAIL_LABEL = "FINALIZER_CPU_GATE_FAIL"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--cmpilot-python", type=Path, required=True)
    parser.add_argument("--vllm-python", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--source-fixture", type=Path, required=True)
    parser.add_argument("--oracle-source", type=Path, required=True)
    parser.add_argument("--job-25692-artifacts", type=Path, required=True)
    parser.add_argument("--model-cache-root", type=Path, required=True)
    parser.add_argument("--expected-environment-fingerprint", required=True)
    parser.add_argument("--expected-runtime-content-digest", required=True)
    parser.add_argument("--expected-model-cache-digest", required=True)
    return parser


def _artifact_directory(arguments: argparse.Namespace) -> Path:
    if arguments.artifact_dir is not None:
        return arguments.artifact_dir
    value = os.environ.get("ARTIFACT_DIR")
    if not value:
        raise RuntimeError("ARTIFACT_DIR is required when --artifact-dir is omitted")
    return Path(value)


def _targeted_tests() -> tuple[str, ...]:
    return (
        "tests/test_calculator_finalizer.py",
        "tests/test_job_25692_forensics.py",
        "tests/test_post_agent_pipeline.py",
        "tests/test_context_budget.py",
        "tests/test_command_authorization.py",
        "tests/test_command_authorization_runtime.py",
        "tests/test_protected_path_policy.py",
        "tests/test_protected_path_runtime.py",
        "tests/test_external_calculator_oracle.py",
        "tests/test_repository_copy_permissions.py",
        "tests/test_working_copy_cpu_job.py",
        "tests/test_action_protocol.py",
        "tests/test_action_protocol_matrix.py",
        "tests/test_batch_script_attestation.py",
        "tests/test_server_command.py",
        "tests/test_shared_runtime.py",
        "tests/test_environment_fingerprint.py",
        "tests/test_environment_content_digest.py",
        "tests/test_environment_load_gate.py",
        "tests/test_smoke_runner.py",
    )


def _run_gate(arguments: argparse.Namespace) -> dict[str, Any]:
    artifact = _artifact_directory(arguments)
    # The shared-runtime wrapper creates this job-owned directory while
    # preserving its own input-verification evidence before the driver starts.
    artifact.mkdir(mode=0o700, parents=True, exist_ok=True)
    project = arguments.project_root.resolve(strict=True)
    source = arguments.source_fixture.resolve(strict=True)
    oracle = arguments.oracle_source.resolve(strict=True)
    historical = arguments.job_25692_artifacts.resolve(strict=True)
    model_cache = arguments.model_cache_root.resolve(strict=True)
    sys.path.insert(0, str(project))
    sys.path.insert(0, str(project / "src"))

    from cmpilot.calculator_finalizer import (
        insert_legacy_shell_state_initialization,
        inspect_shell_finalizer_control_flow,
        require_shell_finalizer_control_flow,
    )
    from cmpilot.finalizer_replay import run_job_25692_stagnation_replay
    from cmpilot.job_25692_forensics import collect_job_25692_forensics
    from scripts.calculator_final_harness_cpu_gate import (
        _cache_fingerprint,
        _capture_environment,
        _remove_scratch_tree,
        _run_process,
        _tree_inventory,
    )

    environment = os.environ.copy()
    scratch = artifact / "scratch"
    scratch.mkdir(mode=0o700)
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": "",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "TMPDIR": str(scratch),
        }
    )
    slurm = {
        "job_id": os.environ.get("SLURM_JOB_ID"),
        "partition": os.environ.get("SLURM_JOB_PARTITION"),
        "nodes": os.environ.get("SLURM_JOB_NUM_NODES"),
        "cpus_per_task": os.environ.get("SLURM_CPUS_PER_TASK"),
        "memory_per_node_mb": os.environ.get("SLURM_MEM_PER_NODE"),
        "job_gpus": os.environ.get("SLURM_JOB_GPUS", ""),
        "cuda_visible_devices": environment["CUDA_VISIBLE_DEVICES"],
    }
    _write_json(artifact / "slurm-resources.json", slurm)
    resource_pass = (
        slurm["partition"] == "Virtual"
        and slurm["nodes"] == "1"
        and slurm["cpus_per_task"] == "2"
        and slurm["memory_per_node_mb"] == "4096"
        and not slurm["job_gpus"]
        and not slurm["cuda_visible_devices"]
    )

    project_before = _tree_inventory(project, ignore_caches=True)
    historical_before = _tree_inventory(historical)
    source_before = _tree_inventory(source)
    environment_initial = _capture_environment(
        "initial",
        artifact=artifact,
        project=project,
        vllm_python=arguments.vllm_python,
        environment=environment,
    )
    cache_initial = _cache_fingerprint(model_cache)
    _write_json(artifact / "model-cache-digest-initial.json", cache_initial)

    forensics = collect_job_25692_forensics(historical)
    _write_json(artifact / "job-25692-forensic-review.json", forensics)
    _write_json(
        artifact / "retrospective-job-25692-capability.json",
        forensics["retrospective_capability"],
    )
    historical_script = (
        historical / "submitted-calculator-diagnostic.sbatch"
    ).read_text(encoding="utf-8")
    corrected_script = insert_legacy_shell_state_initialization(historical_script)
    corrected_control_flow = require_shell_finalizer_control_flow(corrected_script)
    _write_json(
        artifact / "finalizer-variable-control-flow.json",
        {
            "historical": inspect_shell_finalizer_control_flow(
                historical_script
            ),
            "corrected": corrected_control_flow,
        },
    )
    (artifact / "legacy-shell-state-initialization.txt").write_text(
        "POST_AGENT_FAILURE_COUNT=0\n", encoding="ascii", newline="\n"
    )
    (artifact / "job-25692-unbound-variable.stderr").write_text(
        "/var/lib/slurm/slurmd/job25692/slurm_script: line 1196: "
        "POST_AGENT_FAILURE_COUNT: unbound variable\n",
        encoding="utf-8",
        newline="\n",
    )

    targeted = _run_process(
        (
            str(arguments.cmpilot_python),
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            *_targeted_tests(),
        ),
        cwd=project,
        prefix=artifact / "targeted-tests",
        environment=environment,
        timeout=1200,
    )
    _remove_scratch_tree(scratch, job_artifact_root=artifact)
    _write_json(
        artifact / "pre-replay-scratch-cleanup.json",
        {"pass": not scratch.exists(), "complete": not scratch.exists()},
    )

    source_modes = {
        ".": format(stat.S_IMODE(source.stat().st_mode), "04o"),
        "calculator.py": format(
            stat.S_IMODE((source / "calculator.py").stat().st_mode), "04o"
        ),
        "test_calculator.py": format(
            stat.S_IMODE((source / "test_calculator.py").stat().st_mode),
            "04o",
        ),
    }
    _write_json(artifact / "source-modes.json", source_modes)

    integrity_record: dict[str, Any] = {}

    def integrity_callback() -> dict[str, Any]:
        nonlocal integrity_record
        environment_final = _capture_environment(
            "final",
            artifact=artifact,
            project=project,
            vllm_python=arguments.vllm_python,
            environment={**environment, "TMPDIR": str(artifact)},
        )
        cache_final = _cache_fingerprint(model_cache)
        _write_json(artifact / "model-cache-digest-final.json", cache_final)
        project_after = _tree_inventory(project, ignore_caches=True)
        historical_after = _tree_inventory(historical)
        source_after = _tree_inventory(source)
        integrity_record = {
            "pass": all(
                (
                    project_before == project_after,
                    historical_before == historical_after,
                    source_before == source_after,
                    environment_initial["fingerprint"]
                    == environment_final["fingerprint"]
                    == arguments.expected_environment_fingerprint,
                    environment_initial["content_digest"]
                    == environment_final["content_digest"]
                    == arguments.expected_runtime_content_digest,
                    cache_initial["sha256"]
                    == cache_final["sha256"]
                    == arguments.expected_model_cache_digest,
                )
            ),
            "project_unchanged": project_before == project_after,
            "historical_job_25692_unchanged": historical_before
            == historical_after,
            "source_fixture_unchanged": source_before == source_after,
            "environment_fingerprint": environment_final["fingerprint"],
            "runtime_content_digest": environment_final["content_digest"],
            "model_cache_digest": cache_final["sha256"],
        }
        return integrity_record

    prechecks = {
        "cpu_resources": resource_pass,
        "historical_unset_counter_exact": forensics["finalizer_control_flow"][
            "potentially_unset_variables"
        ]
        == ["POST_AGENT_FAILURE_COUNT"],
        "corrected_shell_control_flow": corrected_control_flow["pass"],
        "counter_initialized_before_agent": corrected_control_flow[
            "legacy_counter_initialized_before_agent"
        ],
        "targeted_tests": targeted.returncode == 0,
        "source_fixture_read_only": source_modes
        == {".": "0555", "calculator.py": "0444", "test_calculator.py": "0444"},
    }
    replay = run_job_25692_stagnation_replay(
        source_repository=source,
        oracle_source=oracle,
        output_directory=artifact,
        python=arguments.cmpilot_python,
        integrity_callback=integrity_callback,
        initial_technical_validity=all(prechecks.values()),
        base_result_extra={
            "cpu_gate": "finalizer-robustness-v1",
            "pre_finalization_checks": prechecks,
            "unbound_variable_failures": 0,
        },
        classification_extra={
            "visible_test_execution": "MODEL_TEST_COMMAND_CHOICE",
            "fixture_correction_required": False,
        },
        success_label=PASS_LABEL,
        technical_failure_label=FAIL_LABEL,
    )
    # Do not write beneath the artifact root after total finalization: its
    # self-excluding manifest is now authoritative.
    return {
        "pass": (
            replay["pass"]
            and all(prechecks.values())
            and integrity_record.get("pass") is True
        ),
        "replay": replay,
        "prechecks": prechecks,
        "integrity": integrity_record,
    }


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    artifact = _artifact_directory(arguments)
    try:
        outcome = _run_gate(arguments)
    except BaseException:
        if artifact.exists():
            (artifact / "driver-exception.txt").write_text(
                traceback.format_exc(), encoding="utf-8", newline="\n"
            )
        print(FAIL_LABEL)
        return 1
    passed = outcome["pass"]
    print(PASS_LABEL if passed else FAIL_LABEL)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
