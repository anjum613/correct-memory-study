"""Small, dependency-free probes for an OpenAI-compatible vLLM server."""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ModelProbe:
    endpoint: str
    ok: bool
    diagnostic: str
    status_code: int | None = None
    models: tuple[str, ...] = ()


def models_url(base_url: str) -> str:
    """Normalize supported server/base/models URLs to the ``/v1/models`` endpoint."""
    parsed = urlsplit(base_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("vLLM base URL must be an absolute http(s) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("vLLM base URL must not contain credentials, query parameters, or fragments")

    path = parsed.path.rstrip("/")
    if path.endswith("/models"):
        path = path[: -len("/models")]
    if not path.endswith("/v1"):
        path = f"{path}/v1" if path else "/v1"
    return urlunsplit((parsed.scheme, parsed.netloc, f"{path}/models", "", ""))


def probe_models(base_url: str, *, timeout: float = 5) -> ModelProbe:
    """Fetch ``/v1/models`` and retain a concrete, safe failure cause."""
    try:
        endpoint = models_url(base_url)
    except ValueError as error:
        return ModelProbe("", False, str(error))

    try:
        with urlopen(Request(endpoint, method="GET"), timeout=timeout) as response:  # noqa: S310 - explicit local endpoint
            status = response.status
            if status != 200:
                return ModelProbe(endpoint, False, f"non-200 response: HTTP {status}", status)
            try:
                payload = json.loads(response.read().decode("utf-8"))
                data = payload["data"]
                if not isinstance(data, list):
                    raise TypeError("models data is not a list")
                models = tuple(item["id"] for item in data if isinstance(item, dict) and isinstance(item.get("id"), str))
            except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, AttributeError):
                return ModelProbe(endpoint, False, "invalid JSON from /v1/models", status)
            return ModelProbe(endpoint, True, "endpoint responded", status, models)
    except HTTPError as error:
        return ModelProbe(endpoint, False, f"non-200 response: HTTP {error.code}", error.code)
    except (socket.timeout, TimeoutError):
        return ModelProbe(endpoint, False, "timeout connecting to vLLM")
    except URLError as error:
        reason = str(error.reason).lower()
        if "refused" in reason:
            message = "connection refused"
        elif "timed out" in reason or "timeout" in reason:
            message = "timeout connecting to vLLM"
        else:
            message = f"connection error: {error.reason}"
        return ModelProbe(endpoint, False, message)
    except OSError as error:
        if getattr(error, "errno", None) == 111:
            return ModelProbe(endpoint, False, "connection refused")
        return ModelProbe(endpoint, False, f"connection error: {error}")


def validate_model(probe: ModelProbe, expected_model: str) -> ModelProbe:
    """Return a failed probe when a healthy server lacks the requested model."""
    if not probe.ok or expected_model in probe.models:
        return probe
    return ModelProbe(probe.endpoint, False, f"expected model missing: {expected_model}", probe.status_code, probe.models)
