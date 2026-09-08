"""Read-only forensic extraction for Qwen32B calculator job 25575."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import stat
from typing import Any


FORENSIC_SCHEMA = "qwen32b-calculator-job-25575-forensic-review-v1"


class ForensicEvidenceError(RuntimeError):
    """Raised when authoritative job-25575 evidence is absent or inconsistent."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ForensicEvidenceError(f"could not read {path}: {error}") from error


def _json_lines(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ForensicEvidenceError(f"could not read {path}: {error}") from error
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ForensicEvidenceError(
                f"invalid JSON line {index} in {path}: {error}"
            ) from error
        if not isinstance(value, dict):
            raise ForensicEvidenceError(f"non-object JSON line {index} in {path}")
        records.append(value)
    return records


def _function_evidence(path: Path, name: str) -> dict[str, Any]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]
    if len(functions) != 1:
        raise ForensicEvidenceError(
            f"expected one {name} function in {path}, observed {len(functions)}"
        )
    function = functions[0]
    lines = source.splitlines(keepends=True)
    excerpt = "".join(lines[function.lineno - 1 : function.end_lineno])
    return {
        "file": str(path),
        "function": name,
        "start_line": function.lineno,
        "end_line": function.end_lineno,
        "excerpt_sha256": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
        "excerpt": excerpt,
    }


def _line_window(path: Path, needles: tuple[str, ...], padding: int = 4) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    matched = [
        index
        for index, line in enumerate(lines, start=1)
        if any(needle in line for needle in needles)
    ]
    if not matched:
        raise ForensicEvidenceError(f"none of {needles!r} found in {path}")
    start = max(1, min(matched) - padding)
    end = min(len(lines), max(matched) + padding)
    excerpt = "".join(lines[start - 1 : end])
    return {
        "file": str(path),
        "start_line": start,
        "end_line": end,
        "excerpt_sha256": hashlib.sha256(excerpt.encode("utf-8")).hexdigest(),
        "excerpt": excerpt,
    }


def collect_job_25575_forensics(job_artifacts: Path) -> dict[str, Any]:
    """Collect the requested facts without writing anywhere in the job directory."""
    job_artifacts = job_artifacts.resolve(strict=True)
    if job_artifacts.name != "25575":
        raise ForensicEvidenceError(f"expected job 25575, got {job_artifacts}")
    run_directories = sorted(
        path for path in (job_artifacts / "agent-runs").iterdir() if path.is_dir()
    )
    if len(run_directories) != 1:
        raise ForensicEvidenceError(
            f"expected one agent run, observed {len(run_directories)}"
        )
    run = run_directories[0]
    original = (
        job_artifacts
        / "harness-root"
        / "tasks"
        / "smoke_test"
        / "repository"
        / "test_calculator.py"
    )
    final = run / "working-copy" / "test_calculator.py"
    for path in (original, final):
        if not path.is_file():
            raise ForensicEvidenceError(f"forensic test file missing: {path}")

    patch_history = _json_lines(run / "patch-history.jsonl")
    rewrite_records = [
        record
        for record in patch_history
        if record.get("command_index") == 6
        and "test_calculator.py" in str(record.get("command", ""))
    ]
    if len(rewrite_records) != 1:
        raise ForensicEvidenceError(
            f"expected one command-index-6 test rewrite, observed {len(rewrite_records)}"
        )
    rewrite = rewrite_records[0]
    command = str(rewrite["command"])
    analysis = _json(job_artifacts / "agent-analysis.json")
    transitions = analysis.get("protocol", {}).get("transitions", [])
    transition_matches = [
        transition
        for transition in transitions
        if transition.get("normalized_command") == command
    ]
    if len(transition_matches) != 1:
        raise ForensicEvidenceError(
            f"expected one repository transition for rewrite, observed {len(transition_matches)}"
        )
    transition = transition_matches[0]
    authorization_matches = [
        event
        for event in _json_lines(run / "adapter-events.jsonl")
        if event.get("event") == "command_authorized"
        and event.get("command") == command
    ]
    if len(authorization_matches) != 1:
        raise ForensicEvidenceError(
            f"expected one authorization decision, observed {len(authorization_matches)}"
        )

    analyzer_exit_text = (job_artifacts / "agent-analysis.exit").read_text(
        encoding="utf-8"
    ).strip()
    try:
        analyzer_exit = int(analyzer_exit_text)
    except ValueError as error:
        raise ForensicEvidenceError(
            f"invalid analyzer exit status: {analyzer_exit_text!r}"
        ) from error
    driver = job_artifacts / "calculator-diagnostic-driver.py"
    submitted = (
        job_artifacts
        / "controller-attestation"
        / "source-calculator-diagnostic.sbatch"
    )
    analyzer_function = _function_evidence(driver, "cmd_analyze")
    analyzer_return = _line_window(
        driver,
        (
            "test_unchanged",
            "return 41",
        ),
        padding=3,
    )
    early_stop = _line_window(
        submitted,
        (
            "ANALYSIS_STATUS",
            "independent calculator trajectory or final-validation analysis failed",
            "exit 102",
        ),
        padding=3,
    )

    diff = str(rewrite.get("patch", ""))
    if not diff or "test_calculator.py" not in diff:
        raise ForensicEvidenceError("rewrite record has no test-file diff")
    original_hash = _sha256(original)
    final_hash = _sha256(final)
    expected_original = "f36c3c3f38facdecb8c1c6318976738a16cd6f123d93f67136229ac3cfb759b7"
    expected_final = "4fbbce6b368f418f39f19cd365aa0c3adccac3ee319dc74471d4ae496dcf623a"
    if (original_hash, final_hash) != (expected_original, expected_final):
        raise ForensicEvidenceError(
            "job-25575 test hashes differ from the established artifacts"
        )

    record = {
        "schema": FORENSIC_SCHEMA,
        "job_id": 25575,
        "job_artifacts": str(job_artifacts),
        "agent_run": str(run),
        "original_test": {
            "path": str(original),
            "sha256": original_hash,
            "mode": format(stat.S_IMODE(original.stat().st_mode), "04o"),
        },
        "final_working_tree_test": {
            "path": str(final),
            "sha256": final_hash,
            "mode": format(stat.S_IMODE(final.stat().st_mode), "04o"),
        },
        "exact_textual_diff": diff,
        "semantic_assessment": {
            "classification": "merely_rewritten",
            "assertion_semantics": "unchanged",
            "detail": (
                "The same three add inputs and expected values remain; pytest-style "
                "functions were rewritten as unittest.TestCase methods, additionally "
                "making python -m unittest discover three tests."
            ),
        },
        "modifying_command": {
            "command_index": rewrite["command_index"],
            "command": command,
            "returncode": rewrite.get("returncode"),
            "patch_sha256": rewrite.get("patch_sha256"),
        },
        "repository_transition": {
            "before": transition.get("repository_before"),
            "after": transition.get("repository_after"),
        },
        "authorization_decision": authorization_matches[0],
        "analyzer": {
            "function": analyzer_function,
            "protected_change_return": analyzer_return,
            "return_code": analyzer_exit,
        },
        "early_termination": {
            "shell_code": early_stop,
            "job_exit_code": 102,
            "normal_stages_skipped": [
                "command-authorization audit and shell-history export",
                "top-level final working-tree and patch collection",
                "post-agent GPU and host-memory snapshot",
                "backend import evidence",
                "mini-SWE source-after integrity check",
                "normal shutdown and GPU-release checks",
                "post-calculator project/source/environment/cache checks",
                "memory summary",
                "normal result and dimensional-classification generation",
                "normal artifact-preservation sequence",
            ],
            "trap_cleanup_note": (
                "The EXIT trap performed emergency shutdown and selected integrity "
                "captures, but it did not execute an immutable external oracle or the "
                "complete normal post-agent sequence."
            ),
        },
        "capability_inference_from_modified_suite_prohibited": True,
    }
    if analyzer_exit != 41:
        raise ForensicEvidenceError(f"unexpected analyzer return code: {analyzer_exit}")
    if authorization_matches[0].get("command_category") != "allowed_repository_work":
        raise ForensicEvidenceError("rewrite was not recorded as allowed repository work")
    return record
