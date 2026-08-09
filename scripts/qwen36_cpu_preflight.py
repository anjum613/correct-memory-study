#!/usr/bin/env python3
"""Mandatory CPU-only gate for the pinned Qwen3.6 qualification candidate."""

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
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.qwen36_candidate import (  # noqa: E402
    ARTIFACT_ROOT,
    ENVIRONMENT_PATH,
    FROZEN_TAG,
    FROZEN_TAG_TARGET,
    MODEL_ARCHITECTURE,
    MODEL_ID,
    MODEL_REVISION,
    MODEL_SNAPSHOT,
    QWEN25_RESULT,
    QWEN25_RESULT_SHA256,
    QUALIFICATION_NAMESPACE,
    SELECTED_CONTEXT_LENGTH,
    SOURCE_SUITE,
    SOURCE_SUITE_SHA256,
    build_suite_reference,
    load_json,
    memory_feasibility,
    sha256_file,
    smoke_runtime_path_record,
    validate_snapshot,
    write_canonical_json,
)


CMPILOT_PYTHON = Path("/home/s224049759/environments/cmpilot-conda/bin/python")
VLLM_PYTHON = ENVIRONMENT_PATH / "bin/python"
DEFAULT_OUTPUT = ARTIFACT_ROOT / "cpu-preflight-v4"
_UNRESOLVED = re.compile(r"{{.*?}}|{%.*?%}|\b(?:TODO|TBD|FIXME)\b", re.DOTALL)
_UNQUALIFIED_PYTHON = re.compile(
    r"(?<![/A-Za-z0-9_.-])python(?:3(?:\.\d+)?)?(?=\s|$)"
)
_TEST_SUMMARY = re.compile(
    r"(?P<passed>\d+) passed(?:, (?P<failed>\d+) failed)?(?:, (?P<skipped>\d+) skipped)?"
)


def run(
    argv: Sequence[str], *, cwd: Path, prefix: Path, timeout: int = 3600
) -> dict[str, Any]:
    environment = {
        **os.environ,
        "CUDA_VISIBLE_DEVICES": "",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }
    completed = subprocess.run(
        list(argv),
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        env=environment,
    )
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_suffix(".stdout").write_text(
        completed.stdout or "", encoding="utf-8", newline="\n"
    )
    prefix.with_suffix(".stderr").write_text(
        completed.stderr or "", encoding="utf-8", newline="\n"
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    summary = _TEST_SUMMARY.search(output)
    record = {
        "argv": list(argv),
        "cwd": str(cwd),
        "exit_code": completed.returncode,
        "failed": int(summary.group("failed") or 0) if summary else None,
        "passed": int(summary.group("passed")) if summary else None,
        "skipped": int(summary.group("skipped") or 0) if summary else None,
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


def _component_hashes(candidate: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for component in candidate["protocol_components"]:
        path = ROOT / component["path"]
        actual = sha256_file(path)
        rows.append(
            {
                "actual_sha256": actual,
                "component": component["component"],
                "expected_sha256": component["sha256"],
                "pass": actual == component["sha256"],
                "path": component["path"],
            }
        )
    return {"pass": all(row["pass"] for row in rows), "rows": rows}


def _normalized_suite_reference(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if key != "created_at_utc"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    output = arguments.output_directory
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"CPU preflight output already exists: {output}")
    output.mkdir(parents=True, mode=0o700)
    result: dict[str, Any] = {
        "checks": {},
        "created_at_utc": datetime.now(UTC).isoformat(),
        "overall": "FAIL",
        "schema": "qwen36-qualification-candidate-cpu-preflight-v1",
    }
    try:
        namespace = ROOT / QUALIFICATION_NAMESPACE
        paths = {
            "batch": ROOT / "slurm/qwen36_model_load_request_smoke.sbatch",
            "candidate": namespace / "candidate-freeze-manifest.json",
            "config": namespace / "qualification-config.json",
            "gpu_diagnostic": ROOT / "scripts/capture_gpu_diagnostic.py",
            "interpreter_contract": namespace / "smoke-interpreter-contract.json",
            "environment_content": namespace / "environment-content-digest.json",
            "environment_fingerprint": namespace / "environment-fingerprint.json",
            "metadata": namespace / "model-metadata.json",
            "staging": namespace / "model-staging-manifest.json",
            "suite_reference": namespace / "suite-reference.json",
        }
        for path in paths.values():
            path.resolve(strict=True)

        qwen25_result_sha = sha256_file(ROOT / QWEN25_RESULT)
        qwen25_report = ROOT / "docs/qualification/qwen32b-no-memory-v1-result.md"
        tag = git("rev-list", "-n", "1", FROZEN_TAG)
        history = git("log", "--format=%H", "--", str(QWEN25_RESULT))
        result["qwen25_history"] = {
            "qualification_result_sha256": qwen25_result_sha,
            "report_exists": qwen25_report.is_file(),
            "result_history": history.stdout.splitlines(),
            "tag_target": tag.stdout.strip(),
        }
        result["checks"]["qwen25_failed_result_preserved"] = (
            qwen25_result_sha == QWEN25_RESULT_SHA256
            and qwen25_report.is_file()
            and tag.returncode == 0
            and tag.stdout.strip() == FROZEN_TAG_TARGET
            and history.returncode == 0
            and bool(history.stdout.strip())
        )

        metadata = load_json(paths["metadata"])
        staging = load_json(paths["staging"])
        snapshot = validate_snapshot(MODEL_SNAPSHOT, metadata, hash_weights=True)
        write_canonical_json(output / "snapshot-validation.json", snapshot)
        staging_identity = {
            key: staging["model"][key]
            for key in (
                "chat_template_sha256",
                "config_sha256",
                "generation_config_sha256",
                "revision",
                "snapshot_sha256",
                "tokenizer_inventory_sha256",
                "weight_shard_count",
            )
        }
        snapshot_identity = {key: snapshot[key] for key in staging_identity}
        result["checks"]["pinned_model_snapshot_complete"] = (
            metadata["model_id"] == MODEL_ID
            and metadata["revision"] == MODEL_REVISION
            and snapshot_identity == staging_identity
            and snapshot["architecture"] == MODEL_ARCHITECTURE
        )
        result["model_snapshot"] = snapshot_identity

        environment = run(
            (
                str(VLLM_PYTHON),
                str(ROOT / "scripts/verify_qwen36_environment.py"),
                "--output-directory",
                str(output / "environment-verification"),
                "--expected-fingerprint",
                str(paths["environment_fingerprint"]),
                "--expected-content",
                str(paths["environment_content"]),
            ),
            cwd=ROOT,
            prefix=output / "environment-verification-command",
        )
        environment_result = load_json(output / "environment-verification/result.json")
        result["checks"]["isolated_environment_integrity"] = (
            environment["exit_code"] == 0 and environment_result["pass"] is True
        )
        result["environment_verification"] = environment_result

        contract = load_json(paths["interpreter_contract"])
        project_fingerprint = run(
            (
                str(CMPILOT_PYTHON),
                str(ROOT / "scripts/environment_fingerprint.py"),
                "capture",
                "--inventory",
                str(output / "project-environment-inventory.json"),
                "--record",
                str(output / "project-environment-fingerprint.json"),
            ),
            cwd=ROOT,
            prefix=output / "project-environment-fingerprint-command",
        )
        project_environment = load_json(output / "project-environment-fingerprint.json")
        client_import = run(
            (
                str(VLLM_PYTHON),
                str(ROOT / "scripts/qwen36_smoke_client.py"),
                "--help",
            ),
            cwd=ROOT,
            prefix=output / "smoke-client-import",
        )
        project_dependency_probe = run(
            (
                str(CMPILOT_PYTHON),
                "-c",
                "import importlib.util; "
                "raise SystemExit(0 if importlib.util.find_spec('pydantic') is None else 1)",
            ),
            cwd=ROOT,
            prefix=output / "project-pydantic-absence",
        )
        qwen_dependency_probe = run(
            (
                str(VLLM_PYTHON),
                "-c",
                "import pydantic, torch, transformers, vllm",
            ),
            cwd=ROOT,
            prefix=output / "qwen36-runtime-imports",
        )
        batch_text = paths["batch"].read_text(encoding="utf-8")
        helpers = {row["script"]: row for row in contract.get("helpers", [])}
        project_contract = contract.get("interpreters", {}).get("project_harness", {})
        qwen_contract = contract.get("interpreters", {}).get("qwen36_runtime", {})
        result["checks"]["smoke_interpreter_contract"] = (
            contract.get("schema") == "qwen36-smoke-interpreter-contract-v1"
            and project_fingerprint["exit_code"] == 0
            and project_environment.get("canonical_inventory_sha256")
            == project_contract.get("environment_fingerprint")
            and project_environment.get("interpreter") == str(CMPILOT_PYTHON)
            and qwen_contract.get("environment_fingerprint")
            == "fe63e366ca33bc2392eb173281764bdb8bd543ed3ce8d36c3b3fe6727df80bab"
            and qwen_contract.get("content_digest")
            == "b36b9c47b130dba7c2a0ae60161029d3f5b0b522e8bd0f5b0f0749bae86b3a74"
            and qwen_contract.get("executable") == str(VLLM_PYTHON)
            and client_import["exit_code"] == 0
            and project_dependency_probe["exit_code"] == 0
            and qwen_dependency_probe["exit_code"] == 0
            and helpers.get("scripts/qwen36_smoke_client.py", {}).get(
                "intended_interpreter_role"
            )
            == "qwen36_runtime"
            and batch_text.count(
                '"$VLLM_PY" "$PROJECT/scripts/qwen36_smoke_client.py"'
            )
            == 1
            and '"$CMPILOT_PY" "$PROJECT/scripts/qwen36_smoke_client.py"'
            not in batch_text
            and _UNQUALIFIED_PYTHON.search(batch_text) is None
            and "conda activate" not in batch_text
        )
        result["smoke_interpreter_contract_sha256"] = sha256_file(
            paths["interpreter_contract"]
        )
        result["interpreter_contract"] = {
            "path": str(paths["interpreter_contract"]),
            "project_environment": project_environment,
            "qwen36_client_import_exit_code": client_import["exit_code"],
            "qwen36_runtime_import_exit_code": qwen_dependency_probe["exit_code"],
            "sha256": result["smoke_interpreter_contract_sha256"],
        }

        compatibility = run(
            (
                str(VLLM_PYTHON),
                str(ROOT / "scripts/qwen36_compatibility_probe.py"),
                "--output",
                str(output / "compatibility-result.json"),
            ),
            cwd=ROOT,
            prefix=output / "compatibility-command",
        )
        compatibility_result = load_json(output / "compatibility-result.json")
        result["checks"]["offline_model_and_vllm_compatibility"] = (
            compatibility["exit_code"] == 0 and compatibility_result["pass"] is True
        )
        result["compatibility"] = compatibility_result

        recorded_reference = load_json(paths["suite_reference"])
        observed_reference = build_suite_reference(ROOT)
        suite_reference_match = _normalized_suite_reference(
            recorded_reference
        ) == _normalized_suite_reference(observed_reference)
        write_canonical_json(output / "suite-reference-observed.json", observed_reference)
        result["checks"]["all_seven_frozen_tasks_byte_identical"] = (
            suite_reference_match
            and recorded_reference["all_task_components_byte_identical"] is True
            and len(recorded_reference["tasks"]) == 7
            and sha256_file(ROOT / SOURCE_SUITE) == SOURCE_SUITE_SHA256
        )
        result["suite_reference"] = {
            "recorded_sha256": sha256_file(paths["suite_reference"]),
            "source_suite_sha256": sha256_file(ROOT / SOURCE_SUITE),
            "task_count": len(recorded_reference["tasks"]),
        }

        underlying_gate = run(
            (
                str(CMPILOT_PYTHON),
                str(ROOT / "scripts/qualification_cpu_gate.py"),
                "--suite-manifest",
                str(ROOT / SOURCE_SUITE),
                "--output-directory",
                str(output / "frozen-suite-preflight"),
            ),
            cwd=ROOT,
            prefix=output / "frozen-suite-preflight-command",
            timeout=3600,
        )
        frozen_result = load_json(
            output / "frozen-suite-preflight/cpu-preflight-result.json"
        )
        result["checks"]["complete_frozen_suite_cpu_gate"] = (
            underlying_gate["exit_code"] == 0
            and frozen_result["overall"] == "PASS"
            and all(frozen_result["checks"].values())
        )
        result["frozen_suite_preflight"] = {
            "checks": frozen_result["checks"],
            "overall": frozen_result["overall"],
            "project_tests": frozen_result["project_tests"],
        }

        focused = run(
            (
                str(CMPILOT_PYTHON),
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                "tests/test_qwen36_candidate.py",
                "tests/test_qwen36_smoke_infrastructure.py",
                "tests/test_qwen36_gpu_diagnostic.py",
                "tests/test_qwen36_interpreter_contract.py",
                "tests/test_openai_transport.py",
            ),
            cwd=ROOT,
            prefix=output / "focused-regressions",
        )
        result["checks"]["direct_adapter_parser_policy_regressions"] = (
            focused["exit_code"] == 0 and focused["failed"] == 0
        )
        result["focused_tests"] = focused

        candidate = load_json(paths["candidate"])
        components = _component_hashes(candidate)
        result["checks"]["candidate_component_hashes"] = components["pass"]
        result["component_hashes"] = components
        candidate_sha = sha256_file(paths["candidate"])
        result["candidate_freeze_manifest_sha256"] = candidate_sha
        config = load_json(paths["config"])
        memory = memory_feasibility()
        result["checks"]["bf16_tp2_32k_memory_feasibility"] = (
            memory["pass"] is True
            and config["model"]["context_length"] == SELECTED_CONTEXT_LENGTH
            and config["model"]["tensor_parallel_size"] == 2
            and config["model"]["quantization"] is None
        )
        result["memory_feasibility"] = memory

        runtime = smoke_runtime_path_record("99999999999999999999")
        result["checks"]["runtime_ipc_path_budget"] = (
            runtime["pass"] is True
            and runtime["zmq_socket_path_bytes"] <= 90
            and not runtime["runtime_path_contains_task_id"]
        )
        result["runtime_ipc_path_budget"] = runtime

        bash = run(
            ("/usr/bin/bash", "-n", str(paths["batch"])),
            cwd=ROOT,
            prefix=output / "bash-syntax",
        )
        script = paths["batch"].read_text(encoding="utf-8")
        required_directives = (
            "#SBATCH --partition=gpu",
            "#SBATCH --nodes=1",
            "#SBATCH --ntasks=1",
            "#SBATCH --cpus-per-task=16",
            "#SBATCH --mem=192G",
            "#SBATCH --gres=gpu:a100:2",
            "#SBATCH --no-requeue",
        )
        server_flags = (
            "--dtype bfloat16",
            "--tensor-parallel-size 2",
            "--max-model-len 32768",
            "--max-num-seqs 1",
            "--reasoning-parser qwen3",
            "--language-model-only",
        )
        result["checks"]["controller_attestation_preparation"] = (
            bash["exit_code"] == 0
            and all(script.splitlines().count(item) == 1 for item in required_directives)
            and all(script.count(item) == 2 for item in server_flags)
            and "submit_with_controller_attestation" not in script
        )
        result["controller_attestation"] = {
            "batch_script": str(paths["batch"]),
            "batch_script_sha256": sha256_file(paths["batch"]),
        }
        result["checks"]["gpu_diagnostic_policy"] = (
            "/usr/bin/nvidia-smi -q -d MIG" not in script
            and "--query-gpu=index,name,pci.bus_id,mig.mode.current" in script
            and script.count("--policy informational") == 1
            and 'nvidia-smi > "$ARTIFACT_DIR/nvidia-smi-initial.txt"' in script
            and 'nvidia-smi -L > "$ARTIFACT_DIR/nvidia-smi-list.txt"' in script
            and "scripts/capture_gpu_diagnostic.py" in script
        )

        text_inputs = [
            paths["batch"],
            paths["candidate"],
            paths["config"],
            paths["gpu_diagnostic"],
            paths["interpreter_contract"],
            paths["suite_reference"],
            ROOT / "scripts/qwen36_smoke_client.py",
            ROOT / "scripts/submit_qwen36_smoke.py",
        ]
        unresolved = {
            str(path.relative_to(ROOT)): bool(_UNRESOLVED.search(path.read_text(encoding="utf-8")))
            for path in text_inputs
        }
        result["checks"]["no_unresolved_placeholders"] = not any(unresolved.values())
        result["unresolved_placeholders"] = unresolved
        result["checks"]["gpu_job_requires_no_network_or_install"] = (
            "pip install" not in script
            and "conda install" not in script
            and "snapshot_download" not in script
            and "HF_HUB_OFFLINE=1" in script
            and "TRANSFORMERS_OFFLINE=1" in script
        )
        result["checks"]["no_memory_or_cross_run_state"] = (
            config["treatment"] == "no_memory"
            and candidate["treatment"] == "no_memory"
            and "preserve_thinking" not in script
            and "qnm-p0" not in script
            and "reference-patches" not in script
            and "$SLURM_JOB_ID" in script
        )
        result["checks"]["no_reference_solution_exposure"] = (
            "reference-patches" not in script
            and "reference_patch" not in (ROOT / "scripts/qwen36_smoke_client.py").read_text(
                encoding="utf-8"
            )
            and all(
                set(task) <= {
                    "checks",
                    "immutable_oracle_bundle_sha256",
                    "immutable_oracle_manifest_sha256",
                    "immutable_oracle_test_sha256",
                    "prompt_sha256",
                    "reference_patch_sha256",
                    "repository_source_sha256",
                    "role",
                    "task_description_sha256",
                    "task_id",
                    "task_manifest_path",
                    "task_manifest_sha256",
                    "task_policy_sha256",
                }
                for task in recorded_reference["tasks"]
            )
        )
        result["checks"]["fresh_job_scoped_artifact_path"] = (
            'ARTIFACT_DIR="$ARTIFACT_ROOT/$SLURM_JOB_ID"' in script
            and str(ARTIFACT_ROOT / "smoke/jobs") in script
        )

        compilation = run(
            (
                str(CMPILOT_PYTHON),
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
        diff_check = run(
            ("git", "diff", "--check"),
            cwd=ROOT,
            prefix=output / "git-diff-check",
        )
        result["checks"]["git_diff_check"] = diff_check["exit_code"] == 0
        status = git("status", "--short")
        result["git_status_short"] = status.stdout
        result["checks"]["clean_worktree"] = status.returncode == 0 and not status.stdout
        result["checks"]["cpu_only"] = os.environ.get("CUDA_VISIBLE_DEVICES", "") in {
            "",
            "-1",
        }
        result["checks"]["model_revision_pinned"] = (
            candidate["model"]["id"] == MODEL_ID
            and candidate["model"]["revision"] == MODEL_REVISION
            and candidate["model"]["snapshot_path"] == str(MODEL_SNAPSHOT)
        )
        result["overall"] = "PASS" if all(result["checks"].values()) else "FAIL"
    except BaseException as error:
        result["error"] = f"{type(error).__name__}: {error}"
        result["traceback"] = traceback.format_exc()

    write_canonical_json(output / "cpu-preflight-result.json", result)
    rows = []
    for path in sorted(output.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(output).as_posix()
        if relative in {"artifact-manifest.json", "artifact-manifest.sha256"}:
            continue
        rows.append(
            {"bytes": path.stat().st_size, "path": relative, "sha256": sha256_file(path)}
        )
    manifest = {
        "entry_count": len(rows),
        "files": rows,
        "pass": True,
        "schema": "qwen36-candidate-cpu-preflight-artifact-manifest-v1",
        "self_excluding": True,
    }
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
