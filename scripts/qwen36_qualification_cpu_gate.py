#!/usr/bin/env python3
"""Mandatory post-freeze CPU gate for Qwen3.6 no-memory qualification."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.multiturn_preflight import (  # noqa: E402
    PASS_CLASSIFICATION,
    MultiturnPreflightConfig,
    run_multiturn_preflight,
)
from cmpilot.qwen36_candidate import (  # noqa: E402
    FROZEN_TAG,
    FROZEN_TAG_TARGET,
    MODEL_ARCHITECTURE,
    MODEL_ID,
    MODEL_REVISION,
    MODEL_SNAPSHOT,
    QWEN25_RESULT,
    QWEN25_RESULT_SHA256,
    SELECTED_CONTEXT_LENGTH,
    SOURCE_SUITE,
    SOURCE_SUITE_SHA256,
    build_suite_reference,
    load_json,
    sha256_file,
    validate_snapshot,
)
from cmpilot.qwen36_qualification import (  # noqa: E402
    AGENT_CONFIG,
    ALL_TASKS,
    CANDIDATE_MANIFEST,
    CANDIDATE_MANIFEST_SHA256,
    ENVIRONMENT_CONTENT_DIGEST,
    ENVIRONMENT_FINGERPRINT,
    MAX_OUTPUT_TOKENS,
    MINI_SWE_PYTHON,
    PROJECT_ENVIRONMENT_FINGERPRINT,
    PROJECT_PYTHON,
    QUALIFICATION_FREEZE,
    QWEN36_ARTIFACT_ROOT,
    QWEN36_PYTHON,
    REASONING_PARSER,
    SEED_SCHEDULE,
    SMOKE_RESULT,
    SUITE_REFERENCE,
    SUITE_REFERENCE_SHA256,
    resolved_agent_config,
    validate_agent_config,
    validate_freeze_manifest,
    validate_seed_schedule,
    write_canonical_json,
)
from cmpilot.qualification import artifact_manifest  # noqa: E402
from cmpilot.qualification_runtime_paths import suite_runtime_path_record  # noqa: E402
from scripts.qualification_cpu_gate import _task_gate  # noqa: E402


DEFAULT_OUTPUT = QWEN36_ARTIFACT_ROOT / "cpu-preflight-qualification-freeze"
_TEST_SUMMARY = re.compile(
    r"(?P<passed>\d+) passed(?:, (?P<failed>\d+) failed)?"
    r"(?:, (?P<skipped>\d+) skipped)?"
)
_UNRESOLVED = re.compile(r"@@|{{.*?}}|{%.*?%}|\b(?:TODO|TBD|FIXME)\b", re.DOTALL)


def run(
    argv: Sequence[str],
    *,
    cwd: Path,
    prefix: Path,
    timeout: int = 3600,
) -> dict[str, Any]:
    completed = subprocess.run(
        list(argv),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        env={
            **os.environ,
            "CUDA_VISIBLE_DEVICES": "",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        },
    )
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_suffix(".stdout").write_text(
        completed.stdout or "", encoding="utf-8", newline="\n"
    )
    prefix.with_suffix(".stderr").write_text(
        completed.stderr or "", encoding="utf-8", newline="\n"
    )
    combined = (completed.stdout or "") + (completed.stderr or "")
    match = _TEST_SUMMARY.search(combined)
    record = {
        "argv": list(argv),
        "cwd": str(cwd),
        "exit_code": completed.returncode,
        "failed": int(match.group("failed") or 0) if match else None,
        "passed": int(match.group("passed")) if match else None,
        "skipped": int(match.group("skipped") or 0) if match else None,
        "stderr": str(prefix.with_suffix(".stderr")),
        "stdout": str(prefix.with_suffix(".stdout")),
    }
    write_canonical_json(prefix.with_suffix(".json"), record)
    return record


def git(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", "-C", str(ROOT), *arguments),
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _normalized_suite(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != "created_at_utc"}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _batch_path(task_id: str) -> Path:
    return ROOT / "slurm" / f"qwen36_{task_id.replace('-', '_')}.sbatch"


def _batch_gate(
    output: Path,
    *,
    freeze_sha256: str,
    seeds: dict[str, int],
) -> dict[str, Any]:
    rows = []
    for task_id in ALL_TASKS:
        path = _batch_path(task_id)
        text = path.read_text(encoding="utf-8")
        syntax = run(
            ("/usr/bin/bash", "-n", str(path)),
            cwd=ROOT,
            prefix=output / "batch-syntax" / task_id,
        )
        required = (
            "#SBATCH --partition=gpu",
            "#SBATCH --nodes=1",
            "#SBATCH --ntasks=1",
            "#SBATCH --cpus-per-task=16",
            "#SBATCH --mem=192G",
            "#SBATCH --gres=gpu:a100:2",
            "#SBATCH --no-requeue",
            f"TASK_ID={task_id}",
            f"TASK_SEED={seeds[task_id]}",
            f"EXPECTED_FREEZE_SHA256={freeze_sha256}",
            "--dtype bfloat16",
            "--tensor-parallel-size 2",
            "--max-model-len 32768",
            "--max-num-seqs 1",
            "--gpu-memory-utilization 0.90",
            "--reasoning-parser qwen3",
            "--language-model-only",
            'RUNTIME_SCRATCH=/tmp/cmq-$SLURM_JOB_ID',
            'CMPILOT_PY=/home/s224049759/environments/cmpilot-conda/bin/python',
            'MINI_PY=/home/s224049759/environments/mini-swe-agent-smoke/bin/python',
            'VLLM_PY=/home/s224049759/environments/qwen36-vllm-v1/bin/python',
        )
        forbidden = (
            "pip install",
            "conda install",
            "snapshot_download",
            "reference-patches",
            "memory treatment",
            "procedural memory",
            "python ",
            "python3 ",
            "conda activate",
        )
        row = {
            "path": str(path),
            "sha256": sha256_file(path),
            "syntax_exit_code": syntax["exit_code"],
            "required_fields": all(item in text for item in required),
            "forbidden_fields_absent": all(
                item not in text.casefold() for item in forbidden
            ),
            "offline": "HF_HUB_OFFLINE=1" in text
            and "TRANSFORMERS_OFFLINE=1" in text,
            "no_unresolved_markers": _UNRESOLVED.search(text) is None,
            "scientific_runner": "run_qualification_task.py" in text,
            "fresh_job_artifacts": "$TASK_ID/jobs" in text
            and "$SLURM_JOB_ID" in text,
        }
        row["pass"] = syntax["exit_code"] == 0 and all(
            value for key, value in row.items() if isinstance(value, bool)
        )
        rows.append(row)
    return {"pass": all(row["pass"] for row in rows), "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    output = arguments.output_directory
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"post-freeze CPU gate already exists: {output}")
    output.mkdir(parents=True, mode=0o700)
    result: dict[str, Any] = {
        "checks": {},
        "created_at_utc": datetime.now(UTC).isoformat(),
        "overall": "FAIL",
        "schema": "qwen36-qualification-post-freeze-cpu-gate-v1",
        "treatment": "no_memory",
    }
    try:
        freeze_path = ROOT / QUALIFICATION_FREEZE
        freeze = validate_freeze_manifest(ROOT, freeze_path)
        result["qualification_freeze_sha256"] = freeze["sha256"]
        result["checks"]["qualification_freeze_manifest"] = freeze["pass"] is True

        candidate_sha = sha256_file(ROOT / CANDIDATE_MANIFEST)
        suite_sha = sha256_file(ROOT / SUITE_REFERENCE)
        result["candidate_manifest_sha256"] = candidate_sha
        result["suite_reference_sha256"] = suite_sha
        result["checks"]["candidate_and_suite_reference_immutable"] = (
            candidate_sha == CANDIDATE_MANIFEST_SHA256
            and suite_sha == SUITE_REFERENCE_SHA256
            and sha256_file(ROOT / SOURCE_SUITE) == SOURCE_SUITE_SHA256
        )

        qwen25_sha = sha256_file(ROOT / QWEN25_RESULT)
        tag = git("rev-list", "-n", "1", FROZEN_TAG)
        result["historical_qwen25"] = {
            "qualification_result_sha256": qwen25_sha,
            "tag_target": tag.stdout.strip(),
        }
        result["checks"]["historical_qwen25_result_preserved"] = (
            qwen25_sha == QWEN25_RESULT_SHA256
            and tag.returncode == 0
            and tag.stdout.strip() == FROZEN_TAG_TARGET
        )

        metadata = load_json(ROOT / "qualification/qwen36-v1/model-metadata.json")
        staging = load_json(ROOT / "qualification/qwen36-v1/model-staging-manifest.json")
        snapshot = validate_snapshot(MODEL_SNAPSHOT, metadata, hash_weights=True)
        write_canonical_json(output / "snapshot-validation.json", snapshot)
        fields = (
            "chat_template_sha256",
            "config_sha256",
            "generation_config_sha256",
            "revision",
            "snapshot_sha256",
            "tokenizer_inventory_sha256",
            "weight_shard_count",
        )
        result["checks"]["exact_model_snapshot_complete"] = (
            snapshot["architecture"] == MODEL_ARCHITECTURE
            and snapshot["revision"] == MODEL_REVISION
            and all(snapshot[field] == staging["model"][field] for field in fields)
        )
        result["model_snapshot"] = {field: snapshot[field] for field in fields}

        environment_command = run(
            (
                str(QWEN36_PYTHON),
                str(ROOT / "scripts/verify_qwen36_environment.py"),
                "--output-directory",
                str(output / "qwen-environment-verification"),
                "--expected-fingerprint",
                str(ROOT / "qualification/qwen36-v1/environment-fingerprint.json"),
                "--expected-content",
                str(ROOT / "qualification/qwen36-v1/environment-content-digest.json"),
            ),
            cwd=ROOT,
            prefix=output / "qwen-environment-command",
        )
        environment = load_json(output / "qwen-environment-verification/result.json")
        result["environment_verification"] = environment
        result["checks"]["qwen_environment_integrity"] = (
            environment_command["exit_code"] == 0
            and environment.get("pass") is True
            and environment.get("fingerprint_match") is True
            and environment.get("content", {}).get("actual_content_sha256")
            == ENVIRONMENT_CONTENT_DIGEST
        )

        project_environment = run(
            (
                str(PROJECT_PYTHON),
                str(ROOT / "scripts/environment_fingerprint.py"),
                "capture",
                "--inventory",
                str(output / "project-environment-inventory.json"),
                "--record",
                str(output / "project-environment-fingerprint.json"),
            ),
            cwd=ROOT,
            prefix=output / "project-environment-command",
        )
        project_record = load_json(output / "project-environment-fingerprint.json")
        mini_import = run(
            (
                str(MINI_SWE_PYTHON),
                "-c",
                "import importlib.metadata as m, httpx, minisweagent, pydantic, yaml; "
                "print(m.version('mini-swe-agent'))",
            ),
            cwd=ROOT,
            prefix=output / "mini-swe-imports",
        )
        result["interpreter_mapping"] = {
            "controller": str(PROJECT_PYTHON),
            "mini_swe": str(MINI_SWE_PYTHON),
            "qwen_server": str(QWEN36_PYTHON),
        }
        result["checks"]["project_and_mini_swe_interpreters"] = (
            project_environment["exit_code"] == 0
            and project_record.get("canonical_inventory_sha256")
            == PROJECT_ENVIRONMENT_FINGERPRINT
            and project_record.get("interpreter") == str(PROJECT_PYTHON)
            and mini_import["exit_code"] == 0
            and (output / "mini-swe-imports.stdout").read_text(encoding="utf-8").strip()
            == "2.4.6"
        )

        agent_validation = validate_agent_config(ROOT / AGENT_CONFIG)
        seed_validation = validate_seed_schedule(ROOT / SEED_SCHEDULE)
        seeds = seed_validation["seeds"]
        result["seeds"] = seeds
        result["checks"]["generation_and_seed_freeze"] = (
            agent_validation["pass"] is True
            and seed_validation["pass"] is True
            and agent_validation["model"]["context_limit"]
            == SELECTED_CONTEXT_LENGTH
            and agent_validation["model"]["max_tokens"] == MAX_OUTPUT_TOKENS
            and REASONING_PARSER == "qwen3"
        )

        resolved_mock = output / "mock-resolved-agent-config.json"
        write_canonical_json(
            resolved_mock,
            resolved_agent_config(ROOT, "qnm-p01-interval-merge"),
        )
        mock_directory = output / "scientific-adapter-multiturn"
        mock_exit = run_multiturn_preflight(
            MultiturnPreflightConfig(
                mini_python=str(MINI_SWE_PYTHON),
                artifact_dir=mock_directory,
                timeout_seconds=90,
                model=MODEL_ID,
                tokenizer_path=str(MODEL_SNAPSHOT),
                agent_config_source=resolved_mock,
            )
        )
        mock_result = load_json(mock_directory / "result.json")
        mock_requests = _load_jsonl(mock_directory / "mock-requests.jsonl")
        sampling = {
            "min_p": 0.0,
            "n": 1,
            "presence_penalty": 0.0,
            "repetition_penalty": 1.0,
            "seed": seeds["qnm-p01-interval-merge"],
            "temperature": 1.0,
            "top_k": 20,
            "top_p": 0.95,
        }
        sampling_pass = len(mock_requests) == 3 and all(
            all(row.get("request", {}).get(key) == value for key, value in sampling.items())
            for row in mock_requests
        )
        result["scientific_adapter_mock"] = {
            "classification": mock_result.get("classification"),
            "checks": mock_result.get("checks"),
            "request_count": len(mock_requests),
            "sampling": sampling,
        }
        result["checks"]["scientific_adapter_multiturn_reasoning_boundary"] = (
            mock_exit == 0
            and mock_result.get("classification") == PASS_CLASSIFICATION
            and all(mock_result.get("checks", {}).values())
            and sampling_pass
        )

        recorded_reference = load_json(ROOT / SUITE_REFERENCE)
        observed_reference = build_suite_reference(ROOT)
        write_canonical_json(output / "suite-reference-observed.json", observed_reference)
        result["checks"]["all_seven_task_identities"] = (
            _normalized_suite(recorded_reference)
            == _normalized_suite(observed_reference)
            and recorded_reference.get("all_task_components_byte_identical") is True
            and len(recorded_reference.get("tasks", [])) == 7
        )

        source_suite = load_json(ROOT / SOURCE_SUITE)
        task_records = []
        for suite_task in source_suite["tasks"]:
            task_path = ROOT / suite_task["manifest_path"]
            task = load_json(task_path)
            task_record = _task_gate(ROOT, task, output / "frozen-suite-gate")
            task_record["suite_manifest_hash_match"] = (
                sha256_file(task_path) == suite_task["manifest_sha256"]
            )
            task_record["pass"] = (
                task_record["pass"] and task_record["suite_manifest_hash_match"]
            )
            task_records.append(task_record)
        project_tests = run(
            (
                str(PROJECT_PYTHON),
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
            ),
            cwd=ROOT,
            prefix=output / "complete-project-tests",
            timeout=7200,
        )
        result["frozen_suite_gate"] = {
            "all_task_gates_pass": all(row["pass"] for row in task_records),
            "task_count": len(task_records),
            "tasks": task_records,
        }
        result["project_tests"] = project_tests
        result["checks"]["complete_frozen_suite_and_project_tests"] = (
            len(task_records) == 7
            and all(row["pass"] for row in task_records)
            and project_tests["exit_code"] == 0
            and project_tests["failed"] == 0
        )

        focused = run(
            (
                str(PROJECT_PYTHON),
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "tests/test_qwen36_candidate.py",
                "tests/test_qwen36_gpu_diagnostic.py",
                "tests/test_qwen36_interpreter_contract.py",
                "tests/test_qwen36_smoke_infrastructure.py",
                "tests/test_qwen36_qualification.py",
                "tests/test_openai_transport.py",
                "tests/test_mini_swe_config.py",
                "tests/test_multiturn_preflight.py",
                "tests/test_qualification.py",
                "tests/test_qualification_batch.py",
                "tests/test_context_budget.py",
                "tests/test_action_protocol.py",
                "tests/test_action_protocol_matrix.py",
                "tests/test_command_authorization.py",
                "tests/test_command_authorization_runtime.py",
                "tests/test_protected_path_policy.py",
                "tests/test_protected_path_runtime.py",
                "tests/test_calculator_finalizer.py::test_every_model_termination_path_completes_total_finalization",
            ),
            cwd=ROOT,
            prefix=output / "focused-qwen36-tests",
        )
        result["focused_tests"] = focused
        result["checks"]["focused_qwen36_tests"] = (
            focused["exit_code"] == 0 and focused["failed"] == 0
        )

        suite_manifest = load_json(ROOT / SOURCE_SUITE)
        task_manifests = [
            load_json(ROOT / row["manifest_path"]) for row in suite_manifest["tasks"]
        ]
        runtime = suite_runtime_path_record(
            task_manifests,
            job_ids=("1", "25940", "99999999999999999999"),
        )
        result["runtime_ipc_path_budget"] = runtime
        result["checks"]["runtime_ipc_path_budget"] = runtime["pass"] is True

        batches = _batch_gate(output, freeze_sha256=freeze["sha256"], seeds=seeds)
        result["batches"] = batches
        result["checks"]["all_seven_batches_and_controller_preparation"] = batches[
            "pass"
        ]

        submit_text = (ROOT / "scripts/submit_qwen36_qualification.py").read_text(
            encoding="utf-8"
        )
        result["checks"]["submission_fail_closed_and_treatment_blind"] = (
            "submit_with_controller_attestation" in submit_text
            and "duplicate Qwen3.6 qualification evidence exists" in submit_text
            and "reserves are permitted only for exactly 3/5" in submit_text
            and "treatment\": \"no_memory" in submit_text
            and "reference.patch" not in submit_text
        )

        smoke = load_json(ROOT / SMOKE_RESULT)
        result["checks"]["smoke_25940_pass_and_32k_safe"] = (
            smoke.get("classification") == "PASS"
            and smoke.get("job_id") == "25940"
            and smoke.get("context_decision") == "SAFE_FOR_QUALIFICATION"
            and all(smoke.get("checks", {}).values())
        )

        compilation = run(
            (
                str(PROJECT_PYTHON),
                "-m",
                "compileall",
                "-q",
                "src",
                "scripts",
                "tests",
            ),
            cwd=ROOT,
            prefix=output / "python-compilation",
        )
        result["checks"]["python_compilation"] = compilation["exit_code"] == 0
        diff = run(
            ("git", "diff", "--check"),
            cwd=ROOT,
            prefix=output / "git-diff-check",
        )
        result["checks"]["git_diff_check"] = diff["exit_code"] == 0
        status = git("status", "--short")
        result["git_status_short"] = status.stdout
        result["checks"]["clean_project_worktree"] = (
            status.returncode == 0 and not status.stdout
        )
        result["checks"]["cpu_only"] = os.environ.get("CUDA_VISIBLE_DEVICES", "") in {
            "",
            "-1",
        }
        result["checks"]["no_memory_or_cross_task_state"] = (
            result["treatment"] == "no_memory"
            and all(row.get("treatment") == "no_memory" for row in (
                load_json(ROOT / AGENT_CONFIG),
                load_json(ROOT / SEED_SCHEDULE),
            ) if "treatment" in row)
            and load_json(ROOT / "qualification/qwen36-v1/scientific-adapter-contract.json")
            .get("freshness", {})
            .get("cross_task_reasoning_state") is False
        )
        result["overall"] = "PASS" if all(result["checks"].values()) else "FAIL"
    except BaseException as error:
        result["error"] = f"{type(error).__name__}: {error}"
        result["traceback"] = traceback.format_exc()

    write_canonical_json(output / "cpu-preflight-result.json", result)
    manifest = artifact_manifest(
        output,
        excluded=("artifact-manifest.json", "artifact-manifest.sha256"),
    )
    write_canonical_json(output / "artifact-manifest.json", manifest)
    (output / "artifact-manifest.sha256").write_text(
        sha256_file(output / "artifact-manifest.json") + "\n",
        encoding="ascii",
        newline="\n",
    )
    print(json.dumps({"overall": result["overall"], "output": str(output)}, sort_keys=True))
    return 0 if result["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
