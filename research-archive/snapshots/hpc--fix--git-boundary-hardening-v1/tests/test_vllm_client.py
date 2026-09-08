from __future__ import annotations

import socket
from unittest.mock import patch
from urllib.error import URLError

import pytest

from cmpilot.vllm_client import models_url, probe_models, validate_model


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("http://127.0.0.1:8000", "http://127.0.0.1:8000/v1/models"),
        ("http://127.0.0.1:8000/", "http://127.0.0.1:8000/v1/models"),
        ("http://127.0.0.1:8000/v1", "http://127.0.0.1:8000/v1/models"),
        ("http://127.0.0.1:8000/v1/", "http://127.0.0.1:8000/v1/models"),
        ("http://127.0.0.1:8000/v1/models", "http://127.0.0.1:8000/v1/models"),
    ],
)
def test_models_url_normalizes_supported_forms(base_url: str, expected: str) -> None:
    assert models_url(base_url) == expected


class FakeResponse:
    status = 200

    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


def test_probe_models_calls_v1_models_and_reads_ids() -> None:
    with patch("cmpilot.vllm_client.urlopen", return_value=FakeResponse(b'{"data": [{"id": "smoke"}]}')) as opener:
        result = probe_models("http://127.0.0.1:8000/v1")

    assert result.ok is True
    assert result.models == ("smoke",)
    assert opener.call_args.args[0].full_url == "http://127.0.0.1:8000/v1/models"


def test_probe_models_reports_connection_refusal() -> None:
    with patch("cmpilot.vllm_client.urlopen", side_effect=URLError(ConnectionRefusedError(111, "Connection refused"))):
        result = probe_models("http://127.0.0.1:8000")

    assert result.ok is False
    assert result.diagnostic == "connection refused"


def test_probe_models_reports_timeout_and_invalid_json() -> None:
    with patch("cmpilot.vllm_client.urlopen", side_effect=socket.timeout):
        timeout = probe_models("http://127.0.0.1:8000")
    with patch("cmpilot.vllm_client.urlopen", return_value=FakeResponse(b"not json")):
        invalid_json = probe_models("http://127.0.0.1:8000")

    assert timeout.diagnostic == "timeout connecting to vLLM"
    assert invalid_json.diagnostic == "invalid JSON from /v1/models"


def test_validate_model_reports_missing_expected_model() -> None:
    result = validate_model(
        probe_models_result := type("Probe", (), {
            "endpoint": "http://127.0.0.1:8000/v1/models",
            "ok": True,
            "diagnostic": "endpoint responded",
            "status_code": 200,
            "models": ("other-model",),
        })(),
        "expected-model",
    )

    assert result.ok is False
    assert result.diagnostic == "expected model missing: expected-model"
    assert result.models == probe_models_result.models
