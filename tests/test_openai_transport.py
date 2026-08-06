from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from cmpilot.integrations.miniswe.openai_transport import (
    MessageBoundaryError,
    OpenAIChatTransport,
    TransportHTTPError,
    TransportTimeoutError,
    json_sha256,
    normalize_message,
    normalize_messages,
)
from cmpilot.mock_openai_server import DeterministicOpenAIServer


def test_transport_metadata_is_removed_without_changing_semantic_content() -> None:
    content = "semantic bytes: \x00 Ω\nunchanged"
    normalized = normalize_message(
        {
            "role": "assistant",
            "content": content,
            "extra": {"cost": 0},
            "provider_specific_fields": {"refusal": None},
        },
        "$.messages[2]",
    )

    assert normalized.value == {"role": "assistant", "content": content}
    assert normalized.value["content"].encode() == content.encode()
    assert normalized.excluded_paths == (
        "$.messages[2].extra",
        "$.messages[2].provider_specific_fields",
    )


def test_supported_role_specific_fields_remain() -> None:
    messages, excluded = normalize_messages(
        [
            {"role": "system", "content": "s", "name": "system-name"},
            {"role": "user", "content": "u", "name": "user-name"},
            {
                "role": "assistant",
                "content": "a",
                "name": "assistant-name",
                "tool_calls": [{"id": "call-1", "type": "function"}],
                "function_call": {"name": "legacy"},
            },
            {
                "role": "tool",
                "content": "result",
                "tool_call_id": "call-1",
                "name": "bash",
            },
        ]
    )

    assert excluded == ()
    assert messages[2]["tool_calls"][0]["id"] == "call-1"
    assert messages[2]["function_call"]["name"] == "legacy"
    assert messages[3]["tool_call_id"] == "call-1"


def test_unknown_fields_are_excluded_in_sorted_deterministic_order() -> None:
    message = {
        "role": "user",
        "content": "same",
        "z_unknown": 1,
        "a_unknown": 2,
    }

    first = normalize_message(message, "$.messages[1]")
    second = normalize_message(message, "$.messages[1]")

    assert first == second
    assert first.value == {"role": "user", "content": "same"}
    assert first.excluded_paths == (
        "$.messages[1].a_unknown",
        "$.messages[1].z_unknown",
    )


@pytest.mark.parametrize(
    ("message", "expected_path"),
    [
        ({"role": "assistant", "content": object()}, r"\$\.messages\[4\]\.content"),
        ({"role": "tool", "content": "x"}, r"\$\.messages\[4\]\.tool_call_id"),
        ({"role": "unknown", "content": "x"}, r"\$\.messages\[4\]\.role"),
        (
            {
                "role": "assistant",
                "content": "x",
                "tool_calls": [{"function": object()}],
            },
            r"\$\.messages\[4\]\.tool_calls\[0\]\.function",
        ),
    ],
)
def test_malformed_messages_report_exact_nested_paths(
    message: dict, expected_path: str
) -> None:
    with pytest.raises(MessageBoundaryError, match=expected_path):
        normalize_message(message, "$.messages[4]")


def test_request_hashes_are_deterministic() -> None:
    value = {
        "model": "m",
        "messages": [{"role": "user", "content": "unchanged"}],
        "temperature": 0.0,
        "max_tokens": 10,
    }
    assert json_sha256(value) == json_sha256(dict(reversed(list(value.items()))))


def test_direct_transport_sends_no_authorization_header(tmp_path: Path) -> None:
    with DeterministicOpenAIServer("model", tmp_path / "requests.jsonl") as server:
        result = OpenAIChatTransport(
            server.base_url,
            connect_timeout_seconds=1,
            read_timeout_seconds=1,
        ).complete(
            [{"role": "user", "content": "hello", "extra": {"hidden": True}}],
            model="model",
            temperature=0.0,
            max_tokens=20,
        )

    assert result.status_code == 200
    assert result.excluded_message_paths == ("$.messages[0].extra",)
    assert set(result.request).isdisjoint(
        {
            "guided_choice",
            "guided_decoding_backend",
            "guided_grammar",
            "guided_json",
            "guided_regex",
            "guided_whitespace_pattern",
            "response_format",
            "tool_choice",
            "tools",
        }
    )
    assert result.body["choices"][0]["message"]["provider_specific_fields"]
    assert server.state.requests[0]["authorization_present"] is False
    persisted = (tmp_path / "requests.jsonl").read_text(encoding="utf-8").lower()
    assert "bearer " not in persisted
    assert '"authorization"' not in persisted


class _FailureHandler(BaseHTTPRequestHandler):
    status = 422
    response_body = b'{"error":{"message":"schema rejected exactly"}}'
    delay = 0.0

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        if self.delay:
            time.sleep(self.delay)
        self.send_response(self.status)
        self.send_header("Content-Length", str(len(self.response_body)))
        self.end_headers()
        try:
            self.wfile.write(self.response_body)
        except BrokenPipeError:
            pass

    def log_message(self, format: str, *args: object) -> None:
        return


class _ServerContext:
    def __init__(self, handler: type[BaseHTTPRequestHandler]):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/v1"

    def __enter__(self) -> "_ServerContext":
        self.thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def test_non_2xx_status_and_complete_body_are_preserved() -> None:
    with _ServerContext(_FailureHandler) as server:
        transport = OpenAIChatTransport(
            server.base_url,
            connect_timeout_seconds=1,
            read_timeout_seconds=1,
        )
        with pytest.raises(TransportHTTPError) as raised:
            transport.complete(
                [{"role": "user", "content": "x"}],
                model="model",
                temperature=0.0,
                max_tokens=10,
            )

    assert raised.value.status_code == 422
    assert raised.value.body == _FailureHandler.response_body.decode()
    assert raised.value.artifact_record()["body"] == raised.value.body


def test_request_and_response_hashes_are_deterministic() -> None:
    class StableHandler(_FailureHandler):
        status = 200
        response_body = b'{"choices":[{"message":{"content":"same","role":"assistant"}}]}'

    with _ServerContext(StableHandler) as server:
        transport = OpenAIChatTransport(
            server.base_url,
            connect_timeout_seconds=1,
            read_timeout_seconds=1,
        )
        results = [
            transport.complete(
                [{"role": "user", "content": "same"}],
                model="model",
                temperature=0.0,
                max_tokens=10,
            )
            for _ in range(2)
        ]

    assert results[0].request == results[1].request
    assert results[0].raw_body == results[1].raw_body
    assert results[0].request_sha256 == results[1].request_sha256
    assert results[0].response_sha256 == results[1].response_sha256


def test_read_timeout_is_classified() -> None:
    class SlowHandler(_FailureHandler):
        status = 200
        response_body = b"{}"
        delay = 0.2

    with _ServerContext(SlowHandler) as server:
        transport = OpenAIChatTransport(
            server.base_url,
            connect_timeout_seconds=1,
            read_timeout_seconds=0.02,
        )
        with pytest.raises(TransportTimeoutError) as raised:
            transport.complete(
                [{"role": "user", "content": "x"}],
                model="model",
                temperature=0.0,
                max_tokens=10,
            )

    assert raised.value.classification == "timeout"
    assert raised.value.phase == "response"


def test_endpoint_credentials_are_rejected() -> None:
    with pytest.raises(ValueError, match="no credentials"):
        OpenAIChatTransport(
            "http://user:secret@127.0.0.1:8000/v1",
            connect_timeout_seconds=1,
            read_timeout_seconds=1,
        )
