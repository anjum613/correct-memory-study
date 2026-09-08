"""Deterministic local OpenAI-compatible server for CPU-only adapter tests."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


FIRST_ACTION = (
    "THOUGHT: Inspect the calculator implementation without changing it.\n\n"
    "```mswea_bash_command\n"
    "sed -n '1,160p' calculator.py\n"
    "```"
)
SECOND_ACTION = (
    "THOUGHT: Inspect the calculator tests without changing them.\n\n"
    "```mswea_bash_command\n"
    "sed -n '1,220p' test_calculator.py\n"
    "```"
)
SUBMIT_ACTION = (
    "THOUGHT: The read-only transport check is complete.\n\n"
    "```mswea_bash_command\n"
    "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT\n"
    "```"
)


def _contains_key(value: Any, forbidden: str) -> bool:
    if isinstance(value, dict):
        return forbidden in value or any(_contains_key(item, forbidden) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, forbidden) for item in value)
    return False


class MockState:
    def __init__(self, model: str, record_path: Path):
        self.model = model
        self.record_path = record_path
        self.requests: list[dict[str, Any]] = []
        self.lock = threading.Lock()

    def _write_record(self, record: dict[str, Any]) -> None:
        self.record_path.parent.mkdir(parents=True, exist_ok=True)
        with self.record_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def chat(self, body: Any, *, authorization_present: bool) -> tuple[int, dict[str, Any]]:
        with self.lock:
            request_index = len(self.requests) + 1
            reasons: list[str] = []
            if not isinstance(body, dict):
                reasons.append("request body is not an object")
                messages: list[Any] = []
            else:
                messages = body.get("messages", [])
                if not isinstance(messages, list):
                    reasons.append("messages is not a list")
                    messages = []
                if body.get("model") != self.model:
                    reasons.append("model mismatch")
            if _contains_key(messages, "provider_specific_fields"):
                reasons.append("provider_specific_fields leaked into request history")
            if _contains_key(messages, "extra"):
                reasons.append("extra leaked into request history")
            if _contains_key(messages, "reasoning"):
                reasons.append("reasoning leaked into request history")
            if authorization_present:
                reasons.append("authorization header must not be sent")

            contents = [
                message.get("content", "")
                for message in messages
                if isinstance(message, dict) and isinstance(message.get("content"), str)
            ]
            if request_index >= 2:
                if FIRST_ACTION not in contents:
                    reasons.append("first assistant semantic content is missing")
                if not any("NotImplementedError" in content for content in contents):
                    reasons.append("calculator observation is missing")
            if request_index >= 3:
                if SECOND_ACTION not in contents:
                    reasons.append("second assistant semantic content is missing")
                if not any("test_add" in content for content in contents):
                    reasons.append("calculator-test observation is missing")
            if request_index > 3:
                reasons.append("unexpected extra model request")

            if reasons:
                status = 400
                response = {
                    "error": {
                        "message": "; ".join(reasons),
                        "type": "mock_request_rejected",
                    }
                }
            else:
                status = 200
                content = (FIRST_ACTION, SECOND_ACTION, SUBMIT_ACTION)[request_index - 1]
                response = {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "index": 0,
                            "message": {
                                "content": content,
                                "reasoning": (
                                    "Private mock reasoning for request "
                                    f"{request_index}; it must never re-enter history."
                                ),
                                "provider_specific_fields": {
                                    "mock_transport_metadata": request_index
                                },
                                "role": "assistant",
                            },
                        }
                    ],
                    "created": 0,
                    "id": f"mock-chat-{request_index}",
                    "model": self.model,
                    "object": "chat.completion",
                    "usage": {
                        "completion_tokens": 20 + request_index,
                        "prompt_tokens": 100 + request_index,
                        "total_tokens": 120 + 2 * request_index,
                    },
                }
            record = {
                "accepted": not reasons,
                "authorization_present": authorization_present,
                "request": body,
                "request_index": request_index,
                "response": response,
                "status_code": status,
                "validation_errors": reasons,
            }
            self.requests.append(record)
            self._write_record(record)
            return status, response


class _MockHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "cmpilot-mock-openai/1"

    @property
    def state(self) -> MockState:
        return self.server.mock_state  # type: ignore[attr-defined]

    def _send_json(self, status: int, value: Any) -> None:
        body = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
            return
        if self.path == "/v1/models":
            self._send_json(
                200,
                {
                    "data": [
                        {
                            "created": 0,
                            "id": self.state.model,
                            "object": "model",
                            "owned_by": "cmpilot-mock",
                        }
                    ],
                    "object": "list",
                },
            )
            return
        self._send_json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self._send_json(404, {"error": {"message": "not found"}})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError) as error:
            self._send_json(400, {"error": {"message": f"invalid JSON: {error}"}})
            return
        status, response = self.state.chat(
            body,
            authorization_present="Authorization" in self.headers,
        )
        self._send_json(status, response)

    def log_message(self, format: str, *args: object) -> None:
        return


class DeterministicOpenAIServer:
    """Context-managed thread server; no external model process is started."""

    def __init__(self, model: str, record_path: Path):
        self.state = MockState(model, record_path)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _MockHandler)
        self.server.daemon_threads = True
        self.server.mock_state = self.state  # type: ignore[attr-defined]
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            name="cmpilot-mock-openai",
            daemon=True,
        )

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}/v1"

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    @property
    def stopped(self) -> bool:
        return not self.thread.is_alive()

    def __enter__(self) -> "DeterministicOpenAIServer":
        self.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()
