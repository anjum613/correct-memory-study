"""Strict OpenAI Chat Completions transport with no LiteLLM dependency."""

from __future__ import annotations

import hashlib
import http.client
import json
import math
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import SplitResult, urlsplit


class MessageBoundaryError(ValueError):
    """A message cannot cross the OpenAI-compatible transport boundary."""


class TransportError(RuntimeError):
    """Base class for bounded direct-HTTP transport failures."""

    classification = "transport_error"

    def artifact_record(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "exception_type": type(self).__name__,
            "message": str(self),
        }


class TransportConnectionError(TransportError):
    """The configured endpoint could not be reached."""

    classification = "connection_error"

    def __init__(self, endpoint: str, error: BaseException):
        self.endpoint = endpoint
        self.original_type = type(error).__name__
        super().__init__(f"connection to {endpoint} failed: {error}")

    def artifact_record(self) -> dict[str, Any]:
        return {
            **super().artifact_record(),
            "endpoint": self.endpoint,
            "original_exception_type": self.original_type,
        }


class TransportTimeoutError(TransportError):
    """A connection or response exceeded its configured bound."""

    classification = "timeout"

    def __init__(self, endpoint: str, phase: str):
        self.endpoint = endpoint
        self.phase = phase
        super().__init__(f"{phase} timeout while calling {endpoint}")

    def artifact_record(self) -> dict[str, Any]:
        return {
            **super().artifact_record(),
            "endpoint": self.endpoint,
            "phase": self.phase,
        }


class TransportHTTPError(TransportError):
    """A non-success HTTP response, including its complete response body."""

    classification = "http_status"

    def __init__(
        self,
        *,
        endpoint: str,
        status_code: int,
        body: str,
        request_sha256: str,
        response_sha256: str,
    ):
        self.endpoint = endpoint
        self.status_code = status_code
        self.body = body
        self.request_sha256 = request_sha256
        self.response_sha256 = response_sha256
        super().__init__(f"HTTP {status_code} from {endpoint}: {body}")

    def artifact_record(self) -> dict[str, Any]:
        return {
            **super().artifact_record(),
            "endpoint": self.endpoint,
            "status_code": self.status_code,
            "body": self.body,
            "request_sha256": self.request_sha256,
            "response_sha256": self.response_sha256,
        }


class TransportResponseError(TransportError):
    """A success response was not valid JSON or had an invalid top-level type."""

    classification = "response_schema"

    def __init__(
        self,
        *,
        endpoint: str,
        body: str,
        request_sha256: str,
        response_sha256: str,
        diagnostic: str,
    ):
        self.endpoint = endpoint
        self.body = body
        self.request_sha256 = request_sha256
        self.response_sha256 = response_sha256
        self.diagnostic = diagnostic
        super().__init__(f"invalid response from {endpoint}: {diagnostic}")

    def artifact_record(self) -> dict[str, Any]:
        return {
            **super().artifact_record(),
            "endpoint": self.endpoint,
            "body": self.body,
            "request_sha256": self.request_sha256,
            "response_sha256": self.response_sha256,
            "diagnostic": self.diagnostic,
        }


@dataclass(frozen=True)
class NormalizedMessage:
    value: dict[str, Any]
    excluded_paths: tuple[str, ...]


@dataclass(frozen=True)
class CompletionResult:
    body: dict[str, Any]
    raw_body: str
    status_code: int
    request: dict[str, Any]
    request_sha256: str
    response_sha256: str
    excluded_message_paths: tuple[str, ...]


_FIELDS_BY_ROLE = {
    "system": frozenset({"role", "content", "name"}),
    "user": frozenset({"role", "content", "name"}),
    "assistant": frozenset({"role", "content", "name", "tool_calls", "function_call"}),
    "tool": frozenset({"role", "content", "tool_call_id", "name"}),
}


def _type_name(value: object) -> str:
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"


def _child_path(path: str, key: str) -> str:
    if key.isidentifier():
        return f"{path}.{key}"
    return f"{path}[{json.dumps(key)}]"


def validate_json_data(value: Any, path: str = "$") -> None:
    """Validate an exact JSON-compatible value and report malformed nested paths."""
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise MessageBoundaryError(f"{path}: non-finite float is not JSON-compatible")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            validate_json_data(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise MessageBoundaryError(
                    f"{path}: key {key!r} has type {_type_name(key)}; expected builtins.str"
                )
            validate_json_data(item, _child_path(path, key))
        return
    raise MessageBoundaryError(f"{path}: unsupported value type {_type_name(value)}")


def _require_string(message: dict[str, Any], field: str, path: str) -> str:
    field_path = _child_path(path, field)
    if field not in message:
        raise MessageBoundaryError(f"{field_path}: required field is missing")
    value = message[field]
    if not isinstance(value, str):
        raise MessageBoundaryError(
            f"{field_path}: expected builtins.str, found {_type_name(value)}"
        )
    return value


def normalize_message(message: Any, path: str = "$") -> NormalizedMessage:
    """Keep only role-appropriate OpenAI fields without rewriting content."""
    if not isinstance(message, dict):
        raise MessageBoundaryError(f"{path}: expected dictionary, found {_type_name(message)}")
    for key in message:
        if not isinstance(key, str):
            raise MessageBoundaryError(
                f"{path}: key {key!r} has type {_type_name(key)}; expected builtins.str"
            )

    role = _require_string(message, "role", path)
    if role not in _FIELDS_BY_ROLE:
        raise MessageBoundaryError(
            f"{_child_path(path, 'role')}: unsupported OpenAI message role {role!r}"
        )
    content = _require_string(message, "content", path)
    allowed = _FIELDS_BY_ROLE[role]
    normalized: dict[str, Any] = {"role": role, "content": content}

    if "name" in message:
        normalized["name"] = _require_string(message, "name", path)
    if role == "tool":
        normalized["tool_call_id"] = _require_string(message, "tool_call_id", path)
    if role == "assistant":
        for field in ("tool_calls", "function_call"):
            value = message.get(field)
            if value in (None, [], {}):
                continue
            validate_json_data(value, _child_path(path, field))
            normalized[field] = value

    excluded = tuple(
        _child_path(path, field)
        for field in sorted(message)
        if field not in allowed
    )
    return NormalizedMessage(normalized, excluded)


def normalize_messages(messages: Any, path: str = "$.messages") -> tuple[list[dict[str, Any]], tuple[str, ...]]:
    """Normalize a full history and return deterministic excluded-field paths."""
    if not isinstance(messages, list):
        raise MessageBoundaryError(f"{path}: expected list, found {_type_name(messages)}")
    normalized: list[dict[str, Any]] = []
    excluded: list[str] = []
    for index, message in enumerate(messages):
        item = normalize_message(message, f"{path}[{index}]")
        normalized.append(item.value)
        excluded.extend(item.excluded_paths)
    return normalized, tuple(excluded)


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 JSON used for request and response hashes."""
    validate_json_data(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def json_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _endpoint(base_url: str) -> tuple[SplitResult, str]:
    parsed = urlsplit(base_url.rstrip("/") + "/chat/completions")
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("$.model.base_url: only http and https endpoints are supported")
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("$.model.base_url: endpoint must have a host and contain no credentials, query, or fragment")
    return parsed, parsed.geturl()


class OpenAIChatTransport:
    """One-attempt direct HTTP client for an OpenAI-compatible endpoint."""

    def __init__(self, base_url: str, *, connect_timeout_seconds: float, read_timeout_seconds: float):
        if connect_timeout_seconds <= 0 or read_timeout_seconds <= 0:
            raise ValueError("transport timeouts must be greater than zero")
        self.parsed_endpoint, self.endpoint = _endpoint(base_url)
        self.connect_timeout_seconds = float(connect_timeout_seconds)
        self.read_timeout_seconds = float(read_timeout_seconds)

    def _connection(self) -> http.client.HTTPConnection:
        connection_class = (
            http.client.HTTPSConnection
            if self.parsed_endpoint.scheme == "https"
            else http.client.HTTPConnection
        )
        return connection_class(
            self.parsed_endpoint.hostname,
            self.parsed_endpoint.port,
            timeout=self.connect_timeout_seconds,
        )

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        top_p: float | None = None,
        top_k: int | None = None,
        min_p: float | None = None,
        presence_penalty: float | None = None,
        repetition_penalty: float | None = None,
        seed: int | None = None,
        n: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> CompletionResult:
        normalized, excluded = normalize_messages(messages)
        request_body = {
            "max_tokens": max_tokens,
            "messages": normalized,
            "model": model,
            "temperature": temperature,
        }
        optional_sampling = {
            "top_p": top_p,
            "top_k": top_k,
            "min_p": min_p,
            "presence_penalty": presence_penalty,
            "repetition_penalty": repetition_penalty,
            "seed": seed,
            "n": n,
        }
        request_body.update(
            {name: value for name, value in optional_sampling.items() if value is not None}
        )
        if tools is not None:
            validate_json_data(tools, "$.tools")
            request_body["tools"] = tools
        if tool_choice is not None:
            validate_json_data(tool_choice, "$.tool_choice")
            request_body["tool_choice"] = tool_choice
        request_bytes = canonical_json_bytes(request_body)
        request_hash = hashlib.sha256(request_bytes).hexdigest()
        path = self.parsed_endpoint.path or "/"
        connection = self._connection()
        phase = "connection"
        try:
            connection.request(
                "POST",
                path,
                body=request_bytes,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            phase = "response"
            if connection.sock is not None:
                connection.sock.settimeout(self.read_timeout_seconds)
            response = connection.getresponse()
            raw_bytes = response.read()
        except (TimeoutError, socket.timeout) as error:
            raise TransportTimeoutError(self.endpoint, phase) from error
        except (ConnectionError, OSError, http.client.HTTPException) as error:
            raise TransportConnectionError(self.endpoint, error) from error
        finally:
            connection.close()

        raw_body = raw_bytes.decode("utf-8", errors="replace")
        response_hash = hashlib.sha256(raw_bytes).hexdigest()
        if not 200 <= response.status < 300:
            raise TransportHTTPError(
                endpoint=self.endpoint,
                status_code=response.status,
                body=raw_body,
                request_sha256=request_hash,
                response_sha256=response_hash,
            )
        try:
            parsed_body = json.loads(raw_body)
        except json.JSONDecodeError as error:
            raise TransportResponseError(
                endpoint=self.endpoint,
                body=raw_body,
                request_sha256=request_hash,
                response_sha256=response_hash,
                diagnostic=f"JSON decode failed at character {error.pos}",
            ) from error
        if not isinstance(parsed_body, dict):
            raise TransportResponseError(
                endpoint=self.endpoint,
                body=raw_body,
                request_sha256=request_hash,
                response_sha256=response_hash,
                diagnostic=f"expected JSON object, found {_type_name(parsed_body)}",
            )
        return CompletionResult(
            body=parsed_body,
            raw_body=raw_body,
            status_code=response.status,
            request=request_body,
            request_sha256=request_hash,
            response_sha256=response_hash,
            excluded_message_paths=excluded,
        )
