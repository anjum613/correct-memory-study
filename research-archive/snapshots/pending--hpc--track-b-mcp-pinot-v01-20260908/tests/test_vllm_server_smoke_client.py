"""Unit tests for the vLLM server smoke-test client."""

from __future__ import annotations

import importlib.util
from io import BytesIO
from urllib.error import HTTPError

import pytest
from pathlib import Path


CLIENT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "vllm_server_smoke_client.py"
)


def load_client_module():
    spec = importlib.util.spec_from_file_location(
        "vllm_server_smoke_client_under_test", CLIENT_PATH
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PlainTextHealthResponse:
    """Minimal context-manager response with an intentionally non-JSON body."""

    status = 200
    headers = {"content-type": "text/plain; charset=utf-8", "x-test": "plain-text"}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return b"OK"


def test_plain_text_http_200_health_response_is_accepted(monkeypatch):
    client = load_client_module()
    monkeypatch.setattr(client, "urlopen", lambda request, timeout: PlainTextHealthResponse())

    record = client.probe_health("http://127.0.0.1:8000/health")

    assert record["status_code"] == 200
    assert record["response_text"] == "OK"
    assert record["content_type"] == "text/plain; charset=utf-8"


class JsonResponse:
    def __init__(
        self,
        body: bytes,
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.body = body
        self.status = status
        self.headers = headers or {"content-type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self.body


def test_models_json_response_is_preserved_and_parsed(monkeypatch):
    client = load_client_module()
    body = b'{"data": [{"id": "Qwen/Qwen2.5-Coder-1.5B-Instruct"}]}'
    monkeypatch.setattr(client, "urlopen", lambda request, timeout: JsonResponse(body))

    record = client.request_http("GET", "http://127.0.0.1:8000/v1/models")
    parsed = client.parse_json_response("/v1/models", record)

    assert record["status_code"] == 200
    assert record["body"] == body.decode()
    assert parsed["data"][0]["id"] == "Qwen/Qwen2.5-Coder-1.5B-Instruct"


def test_http_500_body_is_preserved_without_json_parsing(monkeypatch):
    client = load_client_module()
    error = HTTPError(
        "http://127.0.0.1:8000/v1/chat/completions",
        500,
        "Internal Server Error",
        {"content-type": "application/json", "x-request-id": "test-500"},
        BytesIO(b'{"error":"server exploded"}'),
    )
    monkeypatch.setattr(client, "urlopen", lambda request, timeout: (_ for _ in ()).throw(error))
    monkeypatch.setattr(
        client.json,
        "loads",
        lambda body: pytest.fail("non-2xx body must not be JSON-decoded"),
    )

    record = client.request_http(
        "POST",
        "http://127.0.0.1:8000/v1/chat/completions",
        {"model": "smoke"},
        timeout=180,
    )

    assert record["status_code"] == 500
    assert record["headers"]["x-request-id"] == "test-500"
    assert record["body"] == '{"error":"server exploded"}'
    with pytest.raises(RuntimeError, match="/v1/chat/completions failed: 500"):
        client.parse_json_response("/v1/chat/completions", record)


def test_chat_request_timeout_uses_the_configured_timeout(monkeypatch):
    client = load_client_module()
    observed_timeouts: list[float] = []

    def timeout_request(request, timeout):
        observed_timeouts.append(timeout)
        raise TimeoutError("timed out")

    monkeypatch.setattr(client, "urlopen", timeout_request)

    with pytest.raises(TimeoutError, match="timed out"):
        client.request_http(
            "POST",
            "http://127.0.0.1:8000/v1/chat/completions",
            {"model": "smoke"},
            timeout=180,
        )

    assert observed_timeouts == [180]


def test_successful_chat_response_parsing():
    client = load_client_module()
    parsed = client.parse_chat_completion(
        {
            "id": "chatcmpl-smoke",
            "model": "Qwen/Qwen2.5-Coder-1.5B-Instruct",
            "choices": [
                {
                    "message": {
                        "content": (
                            "def safe_divide(a, b):\n"
                            "    if b == 0:\n"
                            "        raise ValueError('b must not be zero')\n"
                            "    return a / b"
                        )
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 21,
                "completion_tokens": 32,
                "total_tokens": 53,
            },
        },
        200,
        "2026-08-02T13:31:00+00:00",
        "2026-08-02T13:31:01+00:00",
        1.0,
    )

    assert parsed["model_returned"] == "Qwen/Qwen2.5-Coder-1.5B-Instruct"
    assert parsed["prompt_token_count"] == 21
    assert parsed["completion_token_count"] == 32
    assert parsed["total_token_count"] == 53
    assert parsed["contains_safe_divide"] is True
    assert parsed["contains_zero_divisor_check"] is True
    assert parsed["contains_value_error"] is True
    assert parsed["output_non_empty"] is True
    assert len(parsed["generated_text_sha256"]) == 64
