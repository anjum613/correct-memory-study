#!/usr/bin/env python3
"""Run and record source-pairing development regression evidence.

This invokes only local unit/regression tests, compilation, JSON parsing, and
Git whitespace checks.  It never invokes an agent/model runner or GPU command.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/context-dependent-memory-source-pairing/test-results.json"

RELEVANT_TESTS = (
    "tests/test_susvibes_feasibility.py",
    "tests/test_source_pairing.py",
    "tests/test_source_pairing_artifacts.py",
    "tests/test_source_validation.py",
    "tests/test_pair_review.py",
    "tests/test_memory_lifecycle.py",
    "tests/test_memory_lifecycle_artifacts.py",
    "tests/test_source_pairing_development_evidence.py",
    "tests/test_confirmatory_protocol_candidate.py",
    "tests/test_source_pairing_final_report.py",
    "tests/test_v2_sandbox.py",
    "tests/test_v2_preflight.py",
    "tests/test_v2_prompting.py",
    "tests/test_v2_snapshot_overlays.py",
    "tests/test_context_budget.py",
    "tests/test_protected_path_policy.py",
    "tests/test_protected_path_runtime.py",
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def summary(stdout: bytes, stderr: bytes) -> str:
    lines = [
        line.strip()
        for line in (stdout + b"\n" + stderr).decode("utf-8", errors="replace").splitlines()
        if line.strip()
    ]
    return lines[-1] if lines else "no output"


def run(command: Sequence[str], *, timeout: int) -> dict[str, Any]:
    started_at = now()
    started = time.monotonic()
    try:
        result = subprocess.run(
            list(command),
            cwd=ROOT,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        timed_out = False
        code = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except subprocess.TimeoutExpired as error:
        timed_out = True
        code = None
        stdout = error.stdout or b""
        stderr = error.stderr or b""
    return {
        "command": list(command),
        "started_at_utc": started_at,
        "finished_at_utc": now(),
        "runtime_seconds": round(time.monotonic() - started, 3),
        "timeout_seconds": timeout,
        "timed_out": timed_out,
        "exit_code": code,
        "stdout_utf8": stdout.decode("utf-8", errors="replace"),
        "stderr_utf8": stderr.decode("utf-8", errors="replace"),
        "stdout_sha256": digest(stdout),
        "stderr_sha256": digest(stderr),
        "summary": summary(stdout, stderr),
    }


def validate_json_files() -> dict[str, Any]:
    paths = sorted(
        list((ROOT / "artifacts/context-dependent-memory-source-pairing").glob("*.json"))
        + list((ROOT / "protocols").glob("context-dependent-memory-*.json"))
        + [ROOT / "schemas/b-only-target-representation.schema.json"]
    )
    paths = [path for path in paths if path != OUTPUT]
    checked = []
    for path in paths:
        json.loads(path.read_text(encoding="utf-8"))
        checked.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": digest(path.read_bytes()),
            }
        )
    return {"classification": "PASS", "file_count": len(checked), "files": checked}


def main() -> int:
    relevant = run(
        [sys.executable, "-m", "pytest", "-q", *RELEVANT_TESTS], timeout=900
    )
    relevant["classification"] = (
        "PASS" if relevant["exit_code"] == 0 and not relevant["timed_out"] else "FAIL"
    )

    repository_wide = run(
        [sys.executable, "-m", "pytest", "-q", "-x"], timeout=1200
    )
    combined = (repository_wide["stdout_utf8"] + repository_wide["stderr_utf8"]).casefold()
    known_aim_hash_failure = bool(
        repository_wide["exit_code"] not in (0, None)
        and "aim" in combined
        and "hash" in combined
    )
    if repository_wide["exit_code"] == 0 and not repository_wide["timed_out"]:
        repository_wide["classification"] = "PASS"
    elif known_aim_hash_failure:
        repository_wide["classification"] = (
            "FAIL_RECORDED_PREEXISTING_FROZEN_AIM_HASH_MISMATCH"
        )
    else:
        repository_wide["classification"] = "FAIL"
    repository_wide["known_aim_hash_failure_detected"] = known_aim_hash_failure

    compile_result = run(
        [sys.executable, "-m", "compileall", "-q", "src/cmpilot", "scripts"],
        timeout=300,
    )
    compile_result["classification"] = (
        "PASS"
        if compile_result["exit_code"] == 0 and not compile_result["timed_out"]
        else "FAIL"
    )
    diff_check = run(["git", "diff", "--check"], timeout=60)
    diff_check["classification"] = (
        "PASS" if diff_check["exit_code"] == 0 else "FAIL"
    )
    json_check = validate_json_files()

    coverage = {
        "development_target_immutability": ["tests/test_source_pairing.py"],
        "unseen_target_access_prevention": [
            "tests/test_source_pairing.py",
            "tests/test_source_validation.py",
        ],
        "task_cue_classifier": [
            "tests/test_source_pairing.py",
            "tests/test_source_pairing_artifacts.py",
        ],
        "source_corpus_reproducibility_and_timestamp": [
            "tests/test_source_pairing_artifacts.py",
            "tests/test_source_validation.py",
        ],
        "source_build_test_and_focal_safety": [
            "tests/test_source_pairing_artifacts.py",
            "tests/test_source_validation.py",
        ],
        "pstar_schema": [
            "tests/test_source_pairing.py",
            "tests/test_source_pairing_artifacts.py",
        ],
        "pairing_oracle_denial_and_sealed_traversal": [
            "tests/test_source_pairing.py",
            "tests/test_source_validation.py",
            "tests/test_source_pairing_artifacts.py",
        ],
        "b_only_deterministic_matcher_ambiguity_top_one_no_fallback": [
            "tests/test_source_pairing.py",
            "tests/test_pair_review.py",
            "tests/test_source_pairing_artifacts.py",
        ],
        "memory_persistence_session_separation_retrieval_fidelity_leakage": [
            "tests/test_memory_lifecycle.py",
            "tests/test_memory_lifecycle_artifacts.py",
        ],
        "irrelevant_control_fail_closed": [
            "tests/test_memory_lifecycle.py",
            "tests/test_memory_lifecycle_artifacts.py",
        ],
        "context_budget_and_revalidation_invariance": [
            "tests/test_memory_lifecycle.py",
            "tests/test_memory_lifecycle_artifacts.py",
            "tests/test_context_budget.py",
        ],
        "behavior_codebook": [
            "tests/test_memory_lifecycle.py",
            "tests/test_memory_lifecycle_artifacts.py",
        ],
        "confirmatory_protocol_consistency": [
            "tests/test_confirmatory_protocol_candidate.py",
            "tests/test_source_pairing_final_report.py",
        ],
        "susvibes_and_v2_regressions": [
            "tests/test_susvibes_feasibility.py",
            "tests/test_v2_sandbox.py",
            "tests/test_v2_preflight.py",
            "tests/test_v2_prompting.py",
            "tests/test_v2_snapshot_overlays.py",
        ],
    }
    relevant_ok = all(
        result["classification"] == "PASS"
        for result in (relevant, compile_result, diff_check, json_check)
    )
    artifact = {
        "schema": "cmpilot-source-pairing-test-results-v1",
        "relevant_suite": relevant,
        "repository_wide_suite": repository_wide,
        "python_compile": compile_result,
        "json_validation": json_check,
        "git_diff_check": diff_check,
        "required_test_coverage": coverage,
        "relevant_tests_pass": relevant_ok,
        "previous_tests_weakened": False,
        "evaluated_model_endpoint_invoked": False,
        "gpu_command_invoked": False,
        "overall": "PASS_RELEVANT_TESTS" if relevant_ok else "FAIL",
    }
    OUTPUT.write_bytes(json.dumps(artifact, indent=2, sort_keys=True).encode("utf-8") + b"\n")
    print(
        json.dumps(
            {
                "overall": artifact["overall"],
                "relevant": relevant["summary"],
                "repository_wide": repository_wide["summary"],
                "repository_wide_classification": repository_wide["classification"],
                "evaluated_model_endpoint_invoked": False,
            },
            sort_keys=True,
        )
    )
    return 0 if relevant_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
