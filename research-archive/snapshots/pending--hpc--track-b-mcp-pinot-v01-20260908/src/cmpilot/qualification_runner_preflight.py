"""CPU-only end-to-end preflight through the actual qualification runner."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from typing import Any

from .artifact_logger import write_json
from .qwen36_candidate import MODEL_ID, MODEL_SNAPSHOT
from .qwen36_qualification import (
    AGENT_CONFIG,
    INFRASTRUCTURE_AMENDMENT,
    MINI_SWE_PYTHON,
    QUALIFICATION_FREEZE,
    SEED_SCHEDULE,
    SUITE_REFERENCE,
)
from .qualification import load_json
from .qualification_runner import QualificationRunConfig, run_qualification_task


FIRST_ACTION = (
    "THOUGHT: Inspect the interval implementation without changing it.\n\n"
    "```mswea_bash_command\n"
    "sed -n '1,200p' intervals.py\n"
    "```"
)
SECOND_ACTION = (
    "THOUGHT: Inspect the visible interval tests without changing them.\n\n"
    "```mswea_bash_command\n"
    "sed -n '1,220p' tests/test_intervals.py\n"
    "```"
)
SUBMIT_ACTION = (
    "THOUGHT: The qualification-runner plumbing check is complete.\n\n"
    "```mswea_bash_command\n"
    "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n"
    "```"
)


def _contains_key(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False


class QualificationMockState:
    def __init__(self, record_path: Path):
        self.record_path = record_path
        self.requests: list[dict[str, Any]] = []
        self.lock = threading.Lock()

    def _record(self, value: dict[str, Any]) -> None:
        self.record_path.parent.mkdir(parents=True, exist_ok=True)
        with self.record_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(value, sort_keys=True) + "\n")

    def chat(self, body: Any, *, authorization_present: bool) -> tuple[int, Any]:
        with self.lock:
            index = len(self.requests) + 1
            errors: list[str] = []
            messages = body.get("messages", []) if isinstance(body, dict) else []
            if not isinstance(body, dict):
                errors.append("request body is not an object")
            if not isinstance(messages, list):
                errors.append("messages is not a list")
                messages = []
            expected_sampling = {
                "min_p": 0.0,
                "n": 1,
                "presence_penalty": 0.0,
                "repetition_penalty": 1.0,
                "seed": 1602021252,
                "temperature": 1.0,
                "top_k": 20,
                "top_p": 0.95,
            }
            if isinstance(body, dict):
                if body.get("model") != MODEL_ID:
                    errors.append("model mismatch")
                for key, expected in expected_sampling.items():
                    if body.get(key) != expected:
                        errors.append(f"sampling mismatch: {key}")
            for forbidden in ("extra", "provider_specific_fields", "reasoning"):
                if _contains_key(messages, forbidden):
                    errors.append(f"{forbidden} leaked into canonical history")
            if authorization_present:
                errors.append("authorization header must be absent")
            contents = [
                message.get("content", "")
                for message in messages
                if isinstance(message, dict)
                and isinstance(message.get("content"), str)
            ]
            if index >= 2:
                if FIRST_ACTION not in contents:
                    errors.append("first assistant action is absent")
                if not any("merge_intervals" in content for content in contents):
                    errors.append("first repository observation is absent")
            if index >= 3:
                if SECOND_ACTION not in contents:
                    errors.append("second assistant action is absent")
                if not any("test_merges_overlapping" in content for content in contents):
                    errors.append("second repository observation is absent")
            if index > 3:
                errors.append("unexpected extra model request")

            if errors:
                status = 400
                response = {
                    "error": {
                        "message": "; ".join(errors),
                        "type": "qualification_mock_rejected",
                    }
                }
            else:
                status = 200
                response = {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "index": 0,
                            "message": {
                                "content": (FIRST_ACTION, SECOND_ACTION, SUBMIT_ACTION)[
                                    index - 1
                                ],
                                "provider_specific_fields": {
                                    "qualification_mock_request": index
                                },
                                "reasoning": (
                                    f"Private Qwen3.6-style mock reasoning turn {index}; "
                                    "it must not re-enter canonical history."
                                ),
                                "role": "assistant",
                            },
                        }
                    ],
                    "created": 0,
                    "id": f"qualification-mock-{index}",
                    "model": MODEL_ID,
                    "object": "chat.completion",
                    "usage": {
                        "completion_tokens": 30 + index,
                        "prompt_tokens": 120 + index,
                        "total_tokens": 150 + 2 * index,
                    },
                }
            record = {
                "accepted": not errors,
                "authorization_present": authorization_present,
                "request": body,
                "request_index": index,
                "response": response,
                "status_code": status,
                "validation_errors": errors,
            }
            self.requests.append(record)
            self._record(record)
            return status, response


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def state(self) -> QualificationMockState:
        return self.server.state  # type: ignore[attr-defined]

    def _send(self, status: int, value: Any) -> None:
        body = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/v1/models":
            self._send(
                200,
                {
                    "data": [{"id": MODEL_ID, "object": "model"}],
                    "object": "list",
                },
            )
        elif self.path == "/health":
            self._send(200, {"status": "ok"})
        else:
            self._send(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/chat/completions":
            self._send(404, {"error": {"message": "not found"}})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError) as error:
            self._send(400, {"error": {"message": f"invalid JSON: {error}"}})
            return
        status, response = self.state.chat(
            body,
            authorization_present="Authorization" in self.headers,
        )
        self._send(status, response)

    def log_message(self, format: str, *args: object) -> None:
        return


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def run_qualification_runner_preflight(project: Path, output: Path) -> dict[str, Any]:
    """Execute p01 through the real runner and adapter using only a CPU mock."""
    project = project.resolve(strict=True)
    output.mkdir(parents=True, exist_ok=False)
    request_path = output / "mock-requests.jsonl"
    state = QualificationMockState(request_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    server.daemon_threads = True
    server.state = state  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    integrity = output / "runtime-integrity.json"
    write_json(integrity, {"pass": True, "scope": "CPU mock qualification runner"})
    artifact = output / "runner-artifact"
    seed_record = load_json(project / SEED_SCHEDULE)
    task_manifest = project / "qualification/qwen32b-v1/tasks/qnm-p01-interval-merge.json"
    source_before = task_manifest.read_bytes()
    runner_exit = 125
    try:
        thread.start()
        host, port = server.server_address
        runner_exit = run_qualification_task(
            QualificationRunConfig(
                project_root=project,
                suite_manifest=project / "qualification/qwen32b-v1/suite-manifest.json",
                suite_reference=project / SUITE_REFERENCE,
                task_manifest=task_manifest,
                freeze_manifest=project / QUALIFICATION_FREEZE,
                infrastructure_amendment=project / INFRASTRUCTURE_AMENDMENT,
                artifact_directory=artifact,
                base_url=f"http://{host}:{port}/v1",
                model=MODEL_ID,
                mini_python=str(MINI_SWE_PYTHON),
                agent_config_source=project / AGENT_CONFIG,
                tokenizer_path=str(MODEL_SNAPSHOT),
                seed=seed_record["seeds"]["qnm-p01-interval-merge"],
                agent_timeout=90,
                server_pid=None,
                runtime_integrity=integrity,
            )
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    requests = state.requests
    transport = _jsonl(artifact / "model-transport.jsonl")
    trajectory = load_json(artifact / "trajectory.json")
    dimensions = load_json(artifact / "outcome-dimensions-pre-finalizer.json")
    no_memory = load_json(artifact / "no-memory-validation.json")
    agent_execution = load_json(artifact / "agent-execution.json")
    resolved = load_json(artifact / "resolved-agent-config.json")
    serialized_histories = [
        json.dumps(row.get("request", {}).get("messages", []), sort_keys=True)
        for row in requests
    ]
    messages = trajectory.get("messages", [])
    checks = {
        "adapter_config_constructed": (
            artifact / "resolved-agent-config.json"
        ).is_file(),
        "agent_config_source_available": resolved.get("model", {}).get("seed")
        == 1602021252,
        "mini_swe_initialized": any(
            row.get("event") == "agent_initialized"
            for row in _jsonl(artifact / "adapter-events.jsonl")
        ),
        "three_model_requests": len(requests) == 3
        and all(row.get("accepted") is True for row in requests),
        "two_turn_observation_propagation": len(requests) >= 3
        and "merge_intervals" in serialized_histories[1]
        and "test_merges_overlapping" in serialized_histories[2],
        "reasoning_excluded_from_history": all(
            '"reasoning"' not in history
            and '"provider_specific_fields"' not in history
            and '"extra"' not in history
            for history in serialized_histories
        ),
        "reasoning_preserved_as_raw_evidence": len(transport) == 3
        and all(
            isinstance(
                row.get("response", {})
                .get("choices", [{}])[0]
                .get("message", {})
                .get("reasoning"),
                str,
            )
            for row in transport
        ),
        "actions_reached_parser": all(
            action in [
                message.get("content")
                for message in messages
                if isinstance(message, dict) and message.get("role") == "assistant"
            ]
            for action in (FIRST_ACTION, SECOND_ACTION, SUBMIT_ACTION)
        ),
        "completion_reached": trajectory.get("info", {}).get("exit_status")
        == "Submitted",
        "runner_technical_path_completed": runner_exit == 0
        and agent_execution.get("exit_code") == 0
        and dimensions.get("technical_validity") is True,
        "functional_result_not_used": dimensions.get("repository_competence") is False,
        "no_memory": no_memory.get("pass") is True
        and no_memory.get("memory_block_present") is False
        and no_memory.get("residual_messages") == 0,
        "fresh_isolated_state": (artifact / "agent-home").is_dir()
        and (artifact / "working-copy").is_dir(),
        "task_identity_unchanged": task_manifest.read_bytes() == source_before,
        "mock_server_stopped": not thread.is_alive(),
    }
    result = {
        "checks": checks,
        "classification": (
            "QUALIFICATION_RUNNER_CPU_MOCK_PASS"
            if all(checks.values())
            else "QUALIFICATION_RUNNER_CPU_MOCK_FAIL"
        ),
        "mock_request_count": len(requests),
        "pass": all(checks.values()),
        "runner_exit_code": runner_exit,
        "schema": "qwen36-qualification-runner-cpu-mock-v1",
        "treatment": "no_memory",
    }
    write_json(output / "result.json", result)
    return result


__all__ = ["run_qualification_runner_preflight"]
