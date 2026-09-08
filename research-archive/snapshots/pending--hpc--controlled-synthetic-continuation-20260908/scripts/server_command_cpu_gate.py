#!/usr/bin/env python3
"""CPU-only Slurm driver for safe Qwen32B server-command extraction."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
from typing import Sequence


PASS_LABEL = "SERVER_COMMAND_CPU_GATE_PASS"
FAIL_LABEL = "SERVER_COMMAND_CPU_GATE_FAIL"
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
    parser.add_argument("--command-plan", type=Path, required=True)
    parser.add_argument("--expected-command-plan-sha256", required=True)
    parser.add_argument("--cmpilot-python", type=Path, required=True)
    return parser


def _run_shell(script: str, path: Path, artifact_dir: Path) -> subprocess.CompletedProcess[bytes]:
    path.write_text(script, encoding="utf-8", newline="\n")
    environment = os.environ.copy()
    environment.update({"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"})
    completed = subprocess.run(
        ["/usr/bin/bash", str(path)],
        env=environment,
        check=False,
        capture_output=True,
        timeout=60,
    )
    (artifact_dir / f"{path.stem}.stdout").write_bytes(completed.stdout)
    (artifact_dir / f"{path.stem}.stderr").write_bytes(completed.stderr)
    return completed


def _decoded_nul(path: Path) -> tuple[str, ...]:
    payload = path.read_bytes()
    if not payload.endswith(b"\0"):
        raise RuntimeError(f"NUL-delimited argv lacks trailing delimiter: {path}")
    return tuple(part.decode("utf-8") for part in payload.split(b"\0")[:-1])


def _run(arguments: argparse.Namespace, artifact_dir: Path) -> dict[str, object]:
    project_root = arguments.project_root.resolve(strict=True)
    sys.path.insert(0, str(project_root / "src"))

    from cmpilot.batch_script_attestation import require_digest_match
    from cmpilot.file_digest import sha256_file
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
        QWEN32B_SNAPSHOT,
        minimal_chat_request,
        run_backend_preflight,
    )
    from cmpilot.server_command import (
        EXTRACTION_FAILURE,
        audit_external_executables,
        expected_qwen32b_server_command,
        load_command_argv,
        render_bash_command_extraction,
        validate_qwen32b_server_command,
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

    dependency_audit = audit_external_executables(scope="cpu", inside_job=True)
    _write_json(artifact_dir / "external-executable-audit.json", dependency_audit)
    if not dependency_audit["pass"] or dependency_audit["jq_required"]:
        raise RuntimeError("mandatory CPU executable audit failed")
    _write_json(
        artifact_dir / "batch-context.json",
        {
            "cuda_visible_devices": os.environ["CUDA_VISIBLE_DEVICES"],
            "driver_path": str(Path(__file__).resolve()),
            "hostname": socket.gethostname(),
            "job_id": os.environ.get("SLURM_JOB_ID"),
            "jq_available": Path("/usr/bin/jq").is_file(),
            "jq_required": False,
            "path": os.environ.get("PATH"),
            "python": sys.executable,
            "schema": "server-command-cpu-batch-context-v1",
        },
    )

    environment_fingerprint = write_fingerprint_artifacts(
        artifact_dir / "environment-inventory-v2.json",
        artifact_dir / "environment-fingerprint-v2.json",
    )
    if environment_fingerprint.sha256 != arguments.expected_environment_fingerprint:
        raise RuntimeError("environment-fingerprint-v2 mismatch")
    content_digest = fingerprint_installed_distributions(CONTENT_DISTRIBUTIONS)
    write_content_digest_artifacts(
        artifact_dir / "environment-content-inventory.json",
        artifact_dir / "environment-content-digest.json",
        content_digest,
    )
    if content_digest.sha256 != arguments.expected_content_digest:
        raise RuntimeError("environment-content-digest mismatch")

    command_plan = arguments.command_plan.resolve(strict=True)
    command_plan_sha256 = sha256_file(command_plan)
    require_digest_match(
        arguments.expected_command_plan_sha256,
        command_plan_sha256,
        context="server-command-plan",
        record=artifact_dir / "server-command-plan-digest-comparison.json",
    )
    submitted_plan = artifact_dir / "submitted-server-command.json"
    submitted_plan.write_bytes(command_plan.read_bytes())
    _write_json(
        artifact_dir / "server-command-plan-integrity.json",
        {
            "expected_sha256": arguments.expected_command_plan_sha256,
            "observed_sha256": command_plan_sha256,
            "path": str(command_plan),
            "schema": "server-command-plan-integrity-v1",
        },
    )
    expected = validate_qwen32b_server_command(load_command_argv(command_plan))
    extraction_dir = artifact_dir / "valid-extraction"
    extraction_dir.mkdir()
    block = render_bash_command_extraction(
        command_json=command_plan,
        artifact_dir=extraction_dir,
        extractor=project_root / "scripts" / "extract_server_command.py",
    )
    valid_shell = _run_shell(
        "#!/usr/bin/bash\nset -euo pipefail\n" + block,
        artifact_dir / "valid-noninteractive-extraction.sh",
        artifact_dir,
    )
    if valid_shell.returncode != 0:
        raise RuntimeError("valid non-interactive Bash extraction failed")
    extracted = _decoded_nul(
        extraction_dir / "server-command-extracted.argv.nul"
    )
    if extracted != expected:
        raise RuntimeError("Bash argv differs from validated JSON command")
    _write_json(
        artifact_dir / "extracted-argument-inventory.json",
        {
            "argument_count": len(extracted),
            "arguments": [
                {"index": index, "value": value}
                for index, value in enumerate(extracted)
            ],
            "schema": "server-command-argument-inventory-v1",
        },
    )

    space_snapshot = artifact_dir / "fixture model path with spaces and 'quote'"
    space_snapshot.mkdir()
    space_command = expected_qwen32b_server_command(
        port=49774, expected_snapshot=space_snapshot
    )
    space_json = artifact_dir / "space-command.json"
    _write_json(space_json, list(space_command))
    space_dir = artifact_dir / "space-extraction"
    space_dir.mkdir()
    space_block = render_bash_command_extraction(
        command_json=space_json,
        artifact_dir=space_dir,
        extractor=project_root / "scripts" / "extract_server_command.py",
        expected_snapshot=space_snapshot,
    )
    space_shell = _run_shell(
        "#!/usr/bin/bash\nset -euo pipefail\n" + space_block,
        artifact_dir / "space-preservation-extraction.sh",
        artifact_dir,
    )
    if space_shell.returncode != 0 or _decoded_nul(
        space_dir / "server-command-extracted.argv.nul"
    ) != space_command:
        raise RuntimeError("space-containing argv was not preserved")

    invalid_evidence: dict[str, object] = {}
    for name, payload in (("empty", "[]\n"), ("malformed", "[\"broken\"\n")):
        source = artifact_dir / f"{name}-command.json"
        source.write_text(payload, encoding="utf-8", newline="\n")
        invalid_dir = artifact_dir / f"{name}-extraction"
        invalid_dir.mkdir()
        invalid_block = render_bash_command_extraction(
            command_json=source,
            artifact_dir=invalid_dir,
            extractor=project_root / "scripts" / "extract_server_command.py",
        )
        completed = _run_shell(
            "#!/usr/bin/bash\nset -euo pipefail\n" + invalid_block,
            artifact_dir / f"{name}-extraction.sh",
            artifact_dir,
        )
        classification = json.loads(
            (invalid_dir / "server-command-extraction-classification.json").read_text()
        )
        stderr = (
            invalid_dir / "server-command-extraction.stderr"
        ).read_text(encoding="utf-8")
        if completed.returncode == 0 or classification["label"] != EXTRACTION_FAILURE:
            raise RuntimeError(f"{name} input did not fail closed")
        if "unbound variable" in stderr:
            raise RuntimeError(f"{name} input lost its primary failure")
        invalid_evidence[name] = {
            "classification": classification,
            "exit_code": completed.returncode,
            "python_stderr": stderr,
        }
    _write_json(artifact_dir / "invalid-input-evidence.json", invalid_evidence)

    request = minimal_chat_request()
    preflight = run_backend_preflight(
        expected, request, tokenizer_path=QWEN32B_SNAPSHOT
    )
    _write_json(artifact_dir / "backend-preflight.json", preflight)
    if preflight["import_result"] != "PASS" or preflight["forbidden_modules"]:
        raise RuntimeError("lm-format-enforcer CPU preflight failed")

    test_command = [
        str(arguments.cmpilot_python),
        "-m",
        "pytest",
        "-q",
        "tests/test_batch_script_attestation.py",
        "tests/test_server_command.py",
        "tests/test_shared_runtime.py",
        "tests/test_environment_content_digest.py",
        "tests/test_guided_backend.py",
        "tests/test_environment_fingerprint.py",
    ]
    _write_json(
        artifact_dir / "targeted-test-command.json",
        {"argv": test_command, "schema": "server-command-targeted-tests-v1"},
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
        raise RuntimeError(f"targeted tests failed with exit {completed.returncode}")

    return {
        "backend_import": preflight["import_path"],
        "backend_import_result": preflight["import_result"],
        "command_plan_sha256": command_plan_sha256,
        "environment_content_digest": content_digest.sha256,
        "environment_fingerprint": environment_fingerprint.sha256,
        "extracted_argument_count": len(extracted),
        "forbidden_modules": preflight["forbidden_modules"],
        "generated_command": shlex.join(expected),
        "jq_required": False,
        "label": PASS_LABEL,
        "server_command_executed": False,
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
            "command_extraction": "PASS",
            "label": PASS_LABEL,
            "model_loading": "NOT_RUN",
            "server_startup": "NOT_RUN",
            "technical_validity": "PASS",
        }
        status = 0
    except Exception as error:
        result = {"error": f"{type(error).__name__}: {error}", "label": FAIL_LABEL}
        classification = {
            "command_extraction": "FAIL",
            "label": FAIL_LABEL,
            "model_loading": "NOT_RUN",
            "server_startup": "NOT_RUN",
            "technical_validity": "FAIL",
        }
        status = 1
    _write_json(artifact_dir / "result.json", result)
    _write_json(artifact_dir / "classification.json", classification)
    print(result["label"], file=sys.stdout if status == 0 else sys.stderr)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
