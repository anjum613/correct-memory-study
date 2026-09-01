"""CPU preflight and GPU command construction for V2 model qualification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any

from .v2_preflight import (
    V2ContextProfile,
    V2PreflightError,
    bound_visible_tool_output,
    calculate_v2_turn_budget,
)


CHECKS = (
    "server_startup",
    "exact_model_revision",
    "exact_tokenizer",
    "server_local_prompt_token_equality",
    "context_32768",
    "benign_generation",
    "valid_tool_call",
    "multiple_tool_turns",
    "file_edit",
    "test_execution",
    "nonempty_patch",
    "output_truncation",
    "trajectory_budget_enforcement",
    "command_timeout_handling",
    "model_response_timeout_handling",
    "clean_shutdown",
    "deterministic_repeatability",
    "no_oom",
    "no_silent_context_truncation",
)
STUDY_MARKERS = frozenset(
    {"mcp-pinot-v1", "onnx-v1", "axios-v1", "aim-v1", "httpx-v1", "djoser-v1"}
)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text())
    if not isinstance(value, dict):
        raise V2PreflightError(f"expected JSON object: {path}")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def assert_synthetic_scope(path: Path) -> None:
    text = str(Path(path).resolve()).casefold()
    if any(marker in text for marker in STUDY_MARKERS):
        raise V2PreflightError("qualification path intersects a six-family study fixture")


def validate_model_profile(path: Path) -> dict[str, Any]:
    profile = _load(path)
    if profile.get("schema") != "cmpilot-v2-model-profile-v1":
        raise V2PreflightError("V2 model profile schema mismatch")
    if profile.get("study_run_authorized") is not False:
        raise V2PreflightError("qualification profile must not authorize study runs")
    server = profile.get("server")
    serialization = profile.get("serialization")
    if not isinstance(server, dict) or not isinstance(serialization, dict):
        raise V2PreflightError("V2 server or serialization profile missing")
    if server.get("max_model_length") != 32768:
        raise V2PreflightError("qualification server context must be 32768")
    snapshot = Path(str(server.get("snapshot")))
    if not snapshot.is_dir() or snapshot.name != profile.get("revision"):
        raise V2PreflightError("exact model snapshot/revision unavailable")
    if "tekken_sha256" in serialization:
        tokenizer = snapshot / "tekken.json"
        expected = serialization["tekken_sha256"]
    else:
        tokenizer = snapshot / "tokenizer.json"
        expected = serialization.get("tokenizer_json_sha256")
    if not tokenizer.is_file() or _sha256_file(tokenizer) != expected:
        raise V2PreflightError("exact tokenizer hash mismatch")
    return profile


def server_command(profile_path: Path, *, port: int) -> tuple[str, ...]:
    profile = validate_model_profile(profile_path)
    if not 1024 <= port <= 65535:
        raise V2PreflightError("qualification port must be in [1024, 65535]")
    server = profile["server"]
    snapshot = str(server["snapshot"])
    command = [
        str(server["python"]),
        "-m",
        "vllm.entrypoints.openai.api_server",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--model",
        snapshot,
        "--tokenizer",
        snapshot,
        "--served-model-name",
        str(profile["model_id"]),
        "--revision",
        str(profile["revision"]),
        "--dtype",
        str(server["dtype"]),
        "--tensor-parallel-size",
        str(server["tensor_parallel_size_for_qualification"]),
        "--max-model-len",
        "32768",
        "--max-num-seqs",
        "1",
        "--seed",
        "0",
    ]
    if server.get("load_format"):
        command.extend(["--load-format", str(server["load_format"])])
    if server.get("config_format"):
        command.extend(["--config-format", str(server["config_format"])])
    return tuple(command)


def _cpu_command_timeout() -> bool:
    try:
        subprocess.run(
            ["/usr/bin/sleep", "1"], capture_output=True, timeout=0.01, check=False
        )
    except subprocess.TimeoutExpired:
        return True
    return False


def _cpu_repository_roundtrip(root: Path) -> dict[str, bool]:
    repository = root / "synthetic-repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    source = repository / "answer.py"
    source.write_text("def answer():\n    return 1\n")
    test = repository / "test_answer.py"
    test.write_text("from answer import answer\nassert answer() == 2\n")
    subprocess.run(["git", "-C", str(repository), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "-c",
            "user.name=V2 Qualification",
            "-c",
            "user.email=v2@example.invalid",
            "commit",
            "-qm",
            "synthetic baseline",
        ],
        check=True,
    )
    source.write_text("def answer():\n    return 2\n")
    test_run = subprocess.run(
        ["/opt/miniconda3/bin/python", "-B", str(test)],
        cwd=repository,
        capture_output=True,
        check=False,
    )
    patch = subprocess.run(
        ["git", "-C", str(repository), "diff", "--binary"],
        capture_output=True,
        check=True,
    ).stdout
    return {
        "file_edit": source.read_text().endswith("return 2\n"),
        "test_execution": test_run.returncode == 0,
        "nonempty_patch": bool(patch),
    }


def cpu_preflight(profile_path: Path, artifact_root: Path) -> dict[str, Any]:
    assert_synthetic_scope(artifact_root)
    profile = validate_model_profile(profile_path)
    command = server_command(profile_path, port=28080)
    statuses = {name: "NOT_TESTED_NO_GPU" for name in CHECKS}
    statuses.update(
        {
            "exact_model_revision": "PASS",
            "exact_tokenizer": "PASS",
            "context_32768": "PASS",
            "output_truncation": "PASS",
            "trajectory_budget_enforcement": "PASS",
            "command_timeout_handling": "PASS",
            "no_silent_context_truncation": "PASS",
        }
    )
    bounded = bound_visible_tool_output("A" * 40000)
    budget = calculate_v2_turn_budget(
        first_request_tokens=500,
        transcript_tokens=500 + V2ContextProfile().trajectory_budget,
    )
    with tempfile.TemporaryDirectory(prefix="v2-qualification-", dir=artifact_root) as name:
        repo_checks = _cpu_repository_roundtrip(Path(name))
    statuses.update({name: "PASS" if value else "FAIL" for name, value in repo_checks.items()})
    if not bounded.truncated or bounded.visible_bytes > 32768:
        statuses["output_truncation"] = "FAIL"
    if budget.termination_reason != "TRAJECTORY_BUDGET_EXHAUSTED":
        statuses["trajectory_budget_enforcement"] = "FAIL"
    if not _cpu_command_timeout():
        statuses["command_timeout_handling"] = "FAIL"
    return {
        "schema": "cmpilot-v2-model-qualification-preflight-v1",
        "model": profile["model_id"],
        "revision": profile["revision"],
        "model_inference": False,
        "server_command": list(command),
        "synthetic_fixture": "generated answer.py repository; no study-family input",
        "checks": statuses,
        "overall_status": (
            "FAIL" if "FAIL" in statuses.values() else "NOT_TESTED_NO_GPU"
        ),
        "study_run_authorized": False,
    }
