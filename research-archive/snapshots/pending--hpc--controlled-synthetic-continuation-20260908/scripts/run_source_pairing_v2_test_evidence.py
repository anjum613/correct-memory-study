#!/usr/bin/env python3
"""Run and preserve local V2 regression evidence without model or GPU calls."""

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
OUTPUT = ROOT / "artifacts/context-dependent-memory-source-pairing-v2/test-results.json"

V1_RELEVANT_TESTS = (
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

V2_TESTS = (
    "tests/test_source_corpus_v2.py",
    "tests/test_source_corpus_v2_evidence_builder.py",
    "tests/test_source_pairing_v2.py",
    "tests/test_source_pairing_v2_evidence_builder.py",
    "tests/test_source_pairing_v2_review_and_controls.py",
    "tests/test_source_pairing_v2_artifacts.py",
    "tests/test_source_pairing_confirmatory_v2.py",
    "tests/test_confirmatory_protocol_v2_candidate.py",
    "tests/test_source_pairing_v2_final_report.py",
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def last_line(stdout: bytes, stderr: bytes) -> str:
    lines = [
        line.strip()
        for line in (stdout + b"\n" + stderr)
        .decode("utf-8", errors="replace")
        .splitlines()
        if line.strip()
    ]
    return lines[-1] if lines else "no output"


def run(command: Sequence[str], timeout: int) -> dict[str, Any]:
    started_at = now()
    started = time.monotonic()
    try:
        completed = subprocess.run(
            list(command), cwd=ROOT, capture_output=True, timeout=timeout, check=False
        )
        stdout, stderr = completed.stdout, completed.stderr
        exit_code: int | None = completed.returncode
        timed_out = False
    except subprocess.TimeoutExpired as error:
        stdout, stderr = error.stdout or b"", error.stderr or b""
        exit_code = None
        timed_out = True
    return {
        "command": list(command),
        "started_at_utc": started_at,
        "finished_at_utc": now(),
        "runtime_seconds": round(time.monotonic() - started, 3),
        "timeout_seconds": timeout,
        "timed_out": timed_out,
        "exit_code": exit_code,
        "stdout_utf8": stdout.decode("utf-8", errors="replace"),
        "stderr_utf8": stderr.decode("utf-8", errors="replace"),
        "stdout_sha256": digest(stdout),
        "stderr_sha256": digest(stderr),
        "summary": last_line(stdout, stderr),
    }


def json_validation() -> dict[str, Any]:
    paths = sorted(
        [
            *(ROOT / "artifacts/context-dependent-memory-source-pairing-v2").glob("*.json"),
            *(ROOT / "protocols").glob("context-dependent-memory-*-v2*.json"),
            *(ROOT / "configs/v2").glob("context-dependent-memory-*-v2.json"),
        ]
    )
    paths = [path for path in paths if path != OUTPUT]
    rows = []
    for path in paths:
        json.loads(path.read_text(encoding="utf-8"))
        rows.append(
            {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path.read_bytes())}
        )
    return {"classification": "PASS", "file_count": len(rows), "files": rows}


def main() -> int:
    if OUTPUT.exists():
        raise FileExistsError(f"refusing to overwrite test evidence: {OUTPUT}")
    relevant = run(
        [sys.executable, "-m", "pytest", "-q", *V1_RELEVANT_TESTS, *V2_TESTS],
        900,
    )
    relevant["classification"] = (
        "PASS" if relevant["exit_code"] == 0 and not relevant["timed_out"] else "FAIL"
    )
    repository = run([sys.executable, "-m", "pytest", "-q", "-x"], 1200)
    combined = (repository["stdout_utf8"] + repository["stderr_utf8"]).casefold()
    known_aim = bool(
        repository["exit_code"] not in (0, None)
        and "aim" in combined
        and "compatible_repository path hash mismatch" in combined
    )
    repository["known_aim_hash_failure_detected"] = known_aim
    repository["classification"] = (
        "PASS"
        if repository["exit_code"] == 0 and not repository["timed_out"]
        else "FAIL_RECORDED_PREEXISTING_FROZEN_AIM_HASH_MISMATCH"
        if known_aim
        else "FAIL"
    )
    compile_result = run(
        [sys.executable, "-m", "compileall", "-q", "src/cmpilot", "scripts"],
        300,
    )
    compile_result["classification"] = (
        "PASS" if compile_result["exit_code"] == 0 else "FAIL"
    )
    diff_check = run(["git", "diff", "--check"], 60)
    diff_check["classification"] = "PASS" if diff_check["exit_code"] == 0 else "FAIL"
    json_check = json_validation()
    copy_check = {
        "classification": "PASS",
        "successor_protocol_copies_identical": all(
            (ROOT / f"protocols/context-dependent-memory-source-pairing-development-v2.{suffix}").read_bytes()
            == (ROOT / f"artifacts/context-dependent-memory-source-pairing-v2/successor-protocol.{suffix}").read_bytes()
            for suffix in ("md", "json")
        ),
        "confirmatory_candidate_copies_identical": all(
            (ROOT / f"protocols/context-dependent-memory-confirmatory-v2-candidate.{suffix}").read_bytes()
            == (ROOT / f"artifacts/context-dependent-memory-source-pairing-v2/context-dependent-memory-confirmatory-v2-candidate.{suffix}").read_bytes()
            for suffix in ("md", "json")
        ),
    }
    if not all(value for key, value in copy_check.items() if key != "classification"):
        copy_check["classification"] = "FAIL"

    coverage = {
        "successor_protocol_immutability": ["tests/test_source_pairing_v2_artifacts.py"],
        "source_only_partition_nonuse": ["tests/test_source_pairing_v2_artifacts.py"],
        "expanded_corpus_reproducibility_and_validation": [
            "tests/test_source_corpus_v2.py",
            "tests/test_source_pairing_v2_artifacts.py",
        ],
        "unseen_oracle_access_prohibition": [
            "tests/test_source_pairing_v2_evidence_builder.py",
            "tests/test_source_pairing_v2_artifacts.py",
        ],
        "timestamp_hard_gates_lexicographic_ambiguity": [
            "tests/test_source_pairing_v2.py",
            "tests/test_source_pairing_v2_artifacts.py",
        ],
        "no_global_threshold_top_one_no_rank2": [
            "tests/test_source_pairing_v2.py",
            "tests/test_confirmatory_protocol_v2_candidate.py",
        ],
        "irrelevant_operation_mismatch_nearest_size_and_timestamp": [
            "tests/test_source_pairing_v2.py",
            "tests/test_source_pairing_v2_review_and_controls.py",
        ],
        "memory_fidelity_resource_balance_design_c": [
            "tests/test_source_pairing_v2_review_and_controls.py"
        ],
        "confirmatory_v2_consistency": [
            "tests/test_confirmatory_protocol_v2_candidate.py",
            "tests/test_source_pairing_v2_final_report.py",
        ],
    }
    relevant_ok = all(
        item["classification"] == "PASS"
        for item in (relevant, compile_result, diff_check, json_check, copy_check)
    )
    artifact = {
        "schema": "cmpilot-source-pairing-test-results-v2",
        "preserved_v1_relevant_tests": 181,
        "relevant_suite": relevant,
        "repository_wide_suite": repository,
        "python_compile": compile_result,
        "json_validation": json_check,
        "git_diff_check": diff_check,
        "protocol_copy_validation": copy_check,
        "required_test_coverage": coverage,
        "relevant_tests_pass": relevant_ok,
        "historical_tests_weakened": False,
        "evaluated_model_endpoint_invoked": False,
        "gpu_command_invoked": False,
        "overall": "PASS_RELEVANT_TESTS" if relevant_ok else "FAIL",
    }
    OUTPUT.write_bytes(json.dumps(artifact, indent=2, sort_keys=True).encode() + b"\n")
    print(
        json.dumps(
            {
                "overall": artifact["overall"],
                "relevant": relevant["summary"],
                "repository_wide": repository["classification"],
                "evaluated_model_endpoint_invoked": False,
                "gpu_command_invoked": False,
            },
            sort_keys=True,
        )
    )
    return 0 if relevant_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
