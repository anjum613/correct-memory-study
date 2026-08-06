#!/usr/bin/env python3
"""CPU-only Slurm driver for the shared-path guided-backend gate."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from typing import Sequence


PASS_LABEL = "GUIDED_BACKEND_SHARED_PATH_GATE_PASS"
FAIL_LABEL = "GUIDED_BACKEND_SHARED_PATH_GATE_FAIL"
EXPECTED_FINGERPRINT_SCHEMA = "environment-fingerprint-v2"
EXPECTED_CONTENT_SCHEMA = "environment-content-digest-v1"
CONTENT_DISTRIBUTIONS = (
    "vllm",
    "outlines",
    "pyairports",
    "lm-format-enforcer",
)


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--expected-environment-fingerprint", required=True)
    parser.add_argument("--expected-content-digest", required=True)
    parser.add_argument("--cmpilot-python", type=Path, required=True)
    return parser


def _run(arguments: argparse.Namespace, artifact_dir: Path) -> dict[str, object]:
    project_root = arguments.project_root.resolve(strict=True)
    sys.path.insert(0, str(project_root / "src"))

    from cmpilot.environment_content_digest import (
        CONTENT_DIGEST_SCHEMA,
        fingerprint_installed_distributions,
        write_content_digest_artifacts,
    )
    from cmpilot.environment_fingerprint import (
        SCHEMA_VERSION,
        write_fingerprint_artifacts,
    )
    from cmpilot.guided_backend import (
        GUIDED_DECODING_BACKEND,
        QWEN32B_SNAPSHOT,
        run_backend_preflight,
        write_qwen32b_load_gate_plan,
    )

    os.environ.update(
        {
            "CUDA_VISIBLE_DEVICES": "",
            "HF_HOME": "/home/s224049759/model-cache/huggingface",
            "HF_HUB_CACHE": "/home/s224049759/model-cache/huggingface/hub",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "HF_HUB_OFFLINE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        }
    )
    if SCHEMA_VERSION != EXPECTED_FINGERPRINT_SCHEMA:
        raise RuntimeError(f"unexpected fingerprint schema: {SCHEMA_VERSION}")
    if CONTENT_DIGEST_SCHEMA != EXPECTED_CONTENT_SCHEMA:
        raise RuntimeError(f"unexpected content-digest schema: {CONTENT_DIGEST_SCHEMA}")

    _write_json(
        artifact_dir / "batch-context.json",
        {
            "cuda_visible_devices": os.environ["CUDA_VISIBLE_DEVICES"],
            "driver_path": str(Path(__file__).resolve()),
            "hostname": socket.gethostname(),
            "job_id": os.environ.get("SLURM_JOB_ID"),
            "lc_all": os.environ.get("LC_ALL"),
            "lang": os.environ.get("LANG"),
            "python": sys.executable,
            "schema": "guided-backend-cpu-batch-context-v1",
        },
    )

    environment_fingerprint = write_fingerprint_artifacts(
        artifact_dir / "environment-inventory-v2.json",
        artifact_dir / "environment-fingerprint-v2.json",
    )
    if environment_fingerprint.sha256 != arguments.expected_environment_fingerprint:
        raise RuntimeError(
            "environment-fingerprint-v2 mismatch: "
            f"expected {arguments.expected_environment_fingerprint}, "
            f"found {environment_fingerprint.sha256}"
        )

    content_digest = fingerprint_installed_distributions(CONTENT_DISTRIBUTIONS)
    write_content_digest_artifacts(
        artifact_dir / "environment-content-inventory.json",
        artifact_dir / "environment-content-digest.json",
        content_digest,
    )
    if content_digest.sha256 != arguments.expected_content_digest:
        raise RuntimeError(
            "environment-content-digest mismatch: "
            f"expected {arguments.expected_content_digest}, found {content_digest.sha256}"
        )

    plan_paths = write_qwen32b_load_gate_plan(
        artifact_dir / "generated-load-gate-plan", port=49773
    )
    command_record = json.loads(plan_paths.command_json.read_text(encoding="utf-8"))
    request = json.loads(plan_paths.request_json.read_text(encoding="utf-8"))
    command = tuple(command_record["argv"])
    if command.count("--guided-decoding-backend") != 1:
        raise RuntimeError("generated command does not have exactly one backend option")
    position = command.index("--guided-decoding-backend")
    if command[position + 1] != GUIDED_DECODING_BACKEND or "outlines" in command:
        raise RuntimeError("generated command did not select only lm-format-enforcer")

    (artifact_dir / "backend-check-started.txt").write_text(
        "GUIDED_BACKEND_CHECK_STARTED\n", encoding="utf-8", newline="\n"
    )
    preflight = run_backend_preflight(
        command, request, tokenizer_path=QWEN32B_SNAPSHOT
    )
    _write_json(artifact_dir / "backend-preflight.json", preflight)
    if preflight["import_result"] != "PASS" or not preflight["processor_is_none"]:
        raise RuntimeError("lm-format-enforcer ordinary request preflight failed")
    if preflight["forbidden_modules"]:
        raise RuntimeError("passing preflight imported Outlines or pyairports")

    test_command = [
        str(arguments.cmpilot_python),
        "-m",
        "pytest",
        "-q",
        "tests/test_shared_runtime.py",
        "tests/test_environment_content_digest.py",
        "tests/test_guided_backend.py",
        "tests/test_environment_fingerprint.py",
    ]
    _write_json(
        artifact_dir / "targeted-test-command.json",
        {"argv": test_command, "schema": "guided-backend-targeted-tests-v1"},
    )
    test_environment = os.environ.copy()
    test_environment["PYTHONPATH"] = str(project_root / "src")
    completed = subprocess.run(
        test_command,
        cwd=project_root,
        env=test_environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=600,
    )
    (artifact_dir / "targeted-tests.stdout").write_text(
        completed.stdout, encoding="utf-8", newline="\n"
    )
    (artifact_dir / "targeted-tests.stderr").write_text(
        completed.stderr, encoding="utf-8", newline="\n"
    )
    if completed.returncode != 0:
        raise RuntimeError(f"targeted regressions failed with exit {completed.returncode}")

    return {
        "backend_import": preflight["import_path"],
        "backend_import_result": preflight["import_result"],
        "backend_option": GUIDED_DECODING_BACKEND,
        "environment_content_digest": content_digest.sha256,
        "environment_content_schema": CONTENT_DIGEST_SCHEMA,
        "environment_fingerprint": environment_fingerprint.sha256,
        "environment_fingerprint_schema": SCHEMA_VERSION,
        "forbidden_modules": preflight["forbidden_modules"],
        "generated_command": command_record["shell"],
        "label": PASS_LABEL,
        "ordinary_processor_is_none": preflight["processor_is_none"],
        "targeted_tests_exit_code": completed.returncode,
    }


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    artifact_dir_value = os.environ.get("ARTIFACT_DIR")
    if not artifact_dir_value:
        print("ARTIFACT_DIR is required", file=sys.stderr)
        return 64
    artifact_dir = Path(artifact_dir_value)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = _run(arguments, artifact_dir)
        classification = {
            "backend_checks_ran": True,
            "label": PASS_LABEL,
            "technical_validity": "PASS",
        }
        status = 0
    except Exception as error:
        result = {
            "error": f"{type(error).__name__}: {error}",
            "label": FAIL_LABEL,
        }
        classification = {
            "backend_checks_ran": (artifact_dir / "backend-check-started.txt").is_file(),
            "label": FAIL_LABEL,
            "technical_validity": "FAIL",
        }
        status = 1
    _write_json(artifact_dir / "result.json", result)
    _write_json(artifact_dir / "classification.json", classification)
    print(result["label"], file=sys.stdout if status == 0 else sys.stderr)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
