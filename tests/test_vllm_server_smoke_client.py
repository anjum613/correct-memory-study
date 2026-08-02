"""Unit tests for the vLLM server smoke-test client."""

from __future__ import annotations

import importlib.util
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
