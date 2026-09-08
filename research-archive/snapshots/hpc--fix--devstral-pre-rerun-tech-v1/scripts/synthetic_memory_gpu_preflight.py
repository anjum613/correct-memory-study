#!/usr/bin/env python3
"""Freeze and CPU-validate the Qwen3.6 synthetic four-condition GPU smoke."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from cmpilot.qwen36_candidate import sha256_file  # noqa: E402
from cmpilot.synthetic_memory_gpu import (  # noqa: E402
    BATCH_PATH,
    GPU_FREEZE_PATH,
    GPU_RESULT_SCHEMA_PATH,
    MODEL_REVISION,
    PREFLIGHT_PATH,
    QUALIFICATION_FREEZE_SHA256,
    QUALIFICATION_RESULT_SHA256,
    SEEDS_PATH,
    SOURCE_CPU_VALIDATION_SHA256,
    SOURCE_MANIFEST_SHA256,
    SOURCE_ROOT,
    SUBMISSION_GATE_SHA256,
    build_gpu_freeze,
    prompt_evidence,
    run_external_check,
    technical_rerun_eligible,
    validate_gpu_freeze,
    validate_memory_semantics,
    validate_seed_schedule,
    validate_source_inventory,
)
from cmpilot.synthetic_memory_smoke import (  # noqa: E402
    CONDITIONS,
    load_json,
    write_canonical_json,
)
from scripts.validate_synthetic_memory_smoke import (  # noqa: E402
    run_oracle_matrix,
    validate_manifest,
)


PROJECT_PYTHON = Path("/home/s224049759/environments/cmpilot-conda/bin/python")
QWEN_PYTHON = Path("/home/s224049759/environments/qwen36-vllm-v1/bin/python")
FOCUSED_SYNTHETIC = (
    "tests/test_synthetic_memory_smoke.py",
    "tests/test_synthetic_memory_gpu_smoke.py",
)
FOCUSED_ADAPTER = (
    "tests/test_openai_transport.py",
    "tests/test_qwen36_qualification.py",
    "tests/test_qwen36_qualification_harness.py",
)


def _run(
    command: list[str],
    *,
    evidence: Path,
    name: str,
    timeout: int = 1800,
    environment: dict[str, str] | None = None,
) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
        env=environment,
    )
    (evidence / f"{name}.stdout").write_text(completed.stdout, encoding="utf-8")
    (evidence / f"{name}.stderr").write_text(completed.stderr, encoding="utf-8")
    (evidence / f"{name}.exit").write_text(
        f"{completed.returncode}\n", encoding="ascii"
    )
    return {
        "argv": command,
        "exit_code": completed.returncode,
        "pass": completed.returncode == 0,
        "stderr_sha256": __import__("hashlib").sha256(
            completed.stderr.encode("utf-8")
        ).hexdigest(),
        "stdout_sha256": __import__("hashlib").sha256(
            completed.stdout.encode("utf-8")
        ).hexdigest(),
    }


def _bash_syntax(evidence: Path) -> dict[str, Any]:
    paths = sorted(ROOT.glob("slurm/*.sbatch")) + sorted(ROOT.glob("scripts/*.sh"))
    rows = []
    for path in paths:
        completed = subprocess.run(
            ["/usr/bin/bash", "-n", str(path)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        rows.append(
            {
                "exit_code": completed.returncode,
                "path": path.relative_to(ROOT).as_posix(),
                "stderr": completed.stderr,
            }
        )
    write_canonical_json(evidence / "bash-syntax.json", {"files": rows})
    return {
        "file_count": len(rows),
        "pass": bool(rows) and all(row["exit_code"] == 0 for row in rows),
    }


def _static_validation() -> dict[str, Any]:
    qualification_path = ROOT / "qualification/qwen36-v1/qualification-result.json"
    qualification = load_json(qualification_path)
    source_cpu_path = ROOT / SOURCE_ROOT / "cpu-validation-result.json"
    source_cpu = load_json(source_cpu_path)
    source = validate_source_inventory(ROOT)
    memory = validate_memory_semantics(ROOT)
    prompts = prompt_evidence(ROOT)
    seeds = validate_seed_schedule(ROOT)
    freeze = validate_gpu_freeze(ROOT)
    result_schema = load_json(ROOT / GPU_RESULT_SCHEMA_PATH)
    batch = (ROOT / BATCH_PATH).read_text(encoding="utf-8")
    runner = (ROOT / "scripts/run_synthetic_memory_gpu_smoke.py").read_text(
        encoding="utf-8"
    )
    qwen_freeze = load_json(
        ROOT / "qualification/qwen36-v1/qualification-freeze-manifest.json"
    )
    frozen_protocol = {
        row["path"]: row["sha256"] for row in qwen_freeze["protocol_components"]
    }
    gpu_protocol = {
        row["path"]: row["sha256"]
        for row in load_json(ROOT / GPU_FREEZE_PATH)["protocol_components"]
    }
    reference_matrix = run_oracle_matrix()
    unpatched_repository = ROOT / SOURCE_ROOT / "repositories/invalidated"
    unpatched = {
        "functional": run_external_check(
            ROOT / SOURCE_ROOT / "oracles/functional_oracle.py",
            unpatched_repository,
        ),
        "security": run_external_check(
            ROOT / SOURCE_ROOT / "oracles/security_witness.py",
            unpatched_repository,
        ),
    }
    unpatched["intended_task_complete"] = bool(
        unpatched["functional"]["pass"] and unpatched["security"]["pass"]
    )
    checks = {
        "assignment_order_and_seeds": seeds["pass"],
        "canonical_submission_gate": sha256_file(
            ROOT / "qualification/qwen36-v1/submission-gate.json"
        )
        == SUBMISSION_GATE_SHA256,
        "condition_complete": set(CONDITIONS)
        == set(load_json(ROOT / SOURCE_ROOT / "assignment.json")["execution_order"]),
        "dynamic_port": "qwen36_server_port.py" in batch
        and "MAX_SERVER_BIND_ATTEMPTS=4" in batch,
        "final_scoring_after_agent": runner.index("functional_post =")
        > runner.index("execution = execute_agent"),
        "four_fresh_agent_calls": "for ordinal, condition in enumerate" in runner
        and "execute_agent(" in runner,
        "freeze": freeze["pass"],
        "frozen_protocol_hashes": gpu_protocol
        == {path: frozen_protocol[path] for path in gpu_protocol},
        "gpu_result_schema": result_schema.get("scientific_evidence") is False
        and len(result_schema.get("condition_dimensions", [])) == 27,
        "memory_semantics": memory["pass"],
        "no_qualification_job": "run_qualification_task.py" not in batch,
        "no_real_triplet": "real security triplet" not in batch.casefold(),
        "one_server": batch.count("vllm.entrypoints.openai.api_server") == 2
        and batch.count("run_synthetic_memory_gpu_smoke.py") == 1,
        "no_unresolved_placeholders": not any(
            marker in batch for marker in ("{{", "}}", "TODO", "TBD", "FIXME")
        ),
        "prompt_equivalence": prompts["pass"],
        "qualification_pass": qualification.get("final_qualification_decision")
        == "PASS"
        and qualification.get("competence_count", {}).get("passed") == 4,
        "qualification_result_hash": sha256_file(qualification_path)
        == QUALIFICATION_RESULT_SHA256,
        "qwen_freeze_hash": sha256_file(
            ROOT / "qualification/qwen36-v1/qualification-freeze-manifest.json"
        )
        == QUALIFICATION_FREEZE_SHA256,
        "reference_matrix": reference_matrix
        == source["manifest"]["expected_reference_matrix"],
        "runtime_ipc": 'RUNTIME_SCRATCH=/tmp/cmq-$SLURM_JOB_ID' in batch,
        "source_cpu_gate": sha256_file(source_cpu_path)
        == SOURCE_CPU_VALIDATION_SHA256
        and source_cpu.get("overall") == "PASS"
        and all(source_cpu.get("checks", {}).values()),
        "source_manifest": sha256_file(ROOT / SOURCE_ROOT / "manifest.json")
        == SOURCE_MANIFEST_SHA256
        and validate_manifest(),
        "source_semantics": source["pass"],
        "technical_rerun_policy": technical_rerun_eligible(
            technical_validity=False
        )
        and not technical_rerun_eligible(technical_validity=True),
        "treatment_only_job": "SYNTHETIC" in batch
        and "qnm-p" not in batch
        and "qnm-r" not in batch,
        "unpatched_target_requires_hardening": unpatched["functional"]["pass"]
        and not unpatched["security"]["pass"]
        and not unpatched["intended_task_complete"],
    }
    return {
        "checks": checks,
        "freeze": freeze,
        "memory": memory,
        "pass": all(checks.values()),
        "prompts": prompts,
        "reference_matrix": reference_matrix,
        "seeds": seeds,
        "source": {"checks": source["checks"], "pass": source["pass"]},
        "unpatched_target": unpatched,
    }


def run_preflight(output_directory: Path, *, execute_tests: bool) -> dict[str, Any]:
    if output_directory.exists() or output_directory.is_symlink():
        raise FileExistsError(f"GPU smoke preflight already exists: {output_directory}")
    output_directory.mkdir(parents=True, mode=0o700)
    static = _static_validation()
    commands: dict[str, Any] = {}
    if execute_tests:
        env = os.environ.copy()
        env.update(
            {
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "NO_PROXY": "127.0.0.1,localhost",
                "no_proxy": "127.0.0.1,localhost",
            }
        )
        commands["focused_synthetic"] = _run(
            [
                str(PROJECT_PYTHON),
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                *FOCUSED_SYNTHETIC,
            ],
            evidence=output_directory,
            name="focused-synthetic",
            environment=env,
        )
        commands["focused_adapter"] = _run(
            [
                str(PROJECT_PYTHON),
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                *FOCUSED_ADAPTER,
            ],
            evidence=output_directory,
            name="focused-adapter",
            environment=env,
        )
        commands["full_project"] = _run(
            [
                str(PROJECT_PYTHON),
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
            ],
            evidence=output_directory,
            name="full-project",
            environment=env,
        )
        commands["python_compile"] = _run(
            [
                str(PROJECT_PYTHON),
                "-m",
                "compileall",
                "-q",
                "src",
                "scripts",
            ],
            evidence=output_directory,
            name="python-compile",
            environment=env,
        )
        commands["git_diff_check"] = _run(
            ["git", "diff", "--check"],
            evidence=output_directory,
            name="git-diff-check",
            environment=env,
        )
        commands["environment"] = _run(
            [
                str(QWEN_PYTHON),
                "scripts/verify_qwen36_environment.py",
                "--output-directory",
                str(output_directory / "environment-verification"),
                "--expected-fingerprint",
                "qualification/qwen36-v1/environment-fingerprint.json",
                "--expected-content",
                "qualification/qwen36-v1/environment-content-digest.json",
            ],
            evidence=output_directory,
            name="environment",
            timeout=600,
            environment=env,
        )
        commands["bash_syntax"] = _bash_syntax(output_directory)
    else:
        commands["runtime_static_only"] = {"pass": True}
    checks = {
        **{f"static_{name}": value for name, value in static["checks"].items()},
        **{f"command_{name}": row["pass"] for name, row in commands.items()},
    }
    result = {
        "batch_sha256": sha256_file(ROOT / BATCH_PATH),
        "checks": checks,
        "commands": commands,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "freeze_sha256": sha256_file(ROOT / GPU_FREEZE_PATH),
        "model_revision": MODEL_REVISION,
        "overall": "PASS" if all(checks.values()) else "FAIL",
        "prompt_evidence": static["prompts"],
        "qualification_result_sha256": QUALIFICATION_RESULT_SHA256,
        "schema": "synthetic-memory-gpu-smoke-preflight-v1",
        "scientific_evidence": False,
        "source_cpu_validation_sha256": SOURCE_CPU_VALIDATION_SHA256,
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "synthetic_seed_schedule_sha256": sha256_file(ROOT / SEEDS_PATH),
    }
    write_canonical_json(output_directory / "preflight-result.json", result)
    print(json.dumps(result, sort_keys=True))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-freeze", action="store_true")
    parser.add_argument("--output-directory", type=Path)
    parser.add_argument("--execute-tests", action="store_true")
    args = parser.parse_args()
    if args.write_freeze:
        write_canonical_json(ROOT / GPU_FREEZE_PATH, build_gpu_freeze(ROOT))
    if args.output_directory is None:
        result = _static_validation()
        print(json.dumps(result, sort_keys=True))
        return 0 if result["pass"] else 1
    result = run_preflight(args.output_directory, execute_tests=args.execute_tests)
    return 0 if result["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
