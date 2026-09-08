"""Read-only forensic extraction for Qwen32B calculator job 25642."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


JOB_ID = "25642"
EXPECTED_ROOT = Path(
    "/home/s224049759/run-artifacts/qwen32b-calculator/25642"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def collect_job_25642_forensics(root: Path = EXPECTED_ROOT) -> dict[str, Any]:
    """Collect evidence without writing to or normalizing historical artifacts."""
    root = root.resolve(strict=True)
    if root.name != JOB_ID:
        raise ValueError(f"expected job-{JOB_ID} artifact directory: {root}")
    run_directories = sorted((root / "agent-runs").glob("smoke-*"))
    if len(run_directories) != 1:
        raise FileNotFoundError(
            f"expected exactly one job-{JOB_ID} agent run, found {len(run_directories)}"
        )
    agent = run_directories[0]
    transport_records = [
        json.loads(line)
        for line in (agent / "model-transport.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    request_15 = transport_records[14]
    trajectory = _json(agent / "trajectory.json")
    canonical_messages = [
        {"role": message["role"], "content": message["content"]}
        for message in trajectory["messages"][:-1]
    ]
    shell_history = _json(root / "actual-shell-command-history.json")
    editor_commands = [
        command
        for command in shell_history["commands"]
        if command in {"nano test_calculator.py", "vim test_calculator.py"}
    ]
    source_script = (
        root / "controller-attestation" / "source-calculator-diagnostic.sbatch"
    )
    lines = source_script.read_text(encoding="utf-8").splitlines()
    broken_line_index = next(
        index
        for index, line in enumerate(lines)
        if '(root/"source-integrity.json").write_text' in line
    )
    broken_excerpt = lines[broken_line_index : broken_line_index + 2]
    if len(broken_excerpt) != 2 or broken_excerpt[1] != '",encoding="utf-8")':
        raise RuntimeError("job-25642 source-integrity failure signature changed")
    source_error = (root / "stderr.log").read_text(
        encoding="utf-8", errors="replace"
    )
    syntax_line = next(
        (line for line in source_error.splitlines() if "SyntaxError:" in line),
        "",
    )
    result = _json(root / "result.json")
    classification = _json(root / "classification.json")
    manifest_validation = _json(root / "manifest-validation.json")
    return {
        "schema": "job-25642-forensic-review-v1",
        "job_id": JOB_ID,
        "artifact_root": str(root),
        "historical_artifacts_modified": False,
        "artifact_manifest_valid": manifest_validation.get("pass") is True,
        "artifact_manifest_sha256": _sha256(root / "SHA256SUMS"),
        "request_context_overflow": {
            "request_index": 15,
            "prompt_tokens": 3696,
            "configured_completion_allowance": 512,
            "possible_total_tokens": 4208,
            "context_limit": 4096,
            "http_status": request_15.get("status_code"),
            "classification": request_15.get("classification"),
            "server_error_body": request_15.get("body"),
            "canonical_message_count": len(canonical_messages),
            "canonical_messages_sha256": hashlib.sha256(
                json.dumps(
                    canonical_messages,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest(),
            "trajectory_exit_status": trajectory["messages"][-1]["extra"][
                "exit_status"
            ],
        },
        "interactive_editor_bypass": {
            "commands": editor_commands,
            "shell_execution_count": len(editor_commands),
            "authorization_at_time": "allowed_repository_work",
            "protected_test_modified": False,
            "filesystem_permissions_prevented_modification": True,
        },
        "source_integrity_generation_failure": {
            "source_script": str(source_script),
            "source_script_sha256": _sha256(source_script),
            "generated_python_line_number": broken_line_index + 1,
            "generated_excerpt": broken_excerpt,
            "syntax_error": syntax_line,
            "interpolated_value": "newline terminator U+000A",
            "cause": (
                "the outer script generator rendered the intended Python string "
                "literal for a newline as a physical newline inside generated source"
            ),
            "pre_submit_gap": (
                "bash -n validates shell syntax but does not compile Python source "
                "embedded in a heredoc"
            ),
        },
        "established_success_dimensions_preserved": True,
        "original_result": result,
        "original_classification": classification,
        "original_classification_rewritten": False,
    }
