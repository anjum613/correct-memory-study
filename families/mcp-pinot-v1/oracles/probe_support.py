"""Dependency-free execution probes for the frozen MCP Pinot family.

The probes import the candidate repository's real ``mcp_pinot.config`` and
``mcp_pinot.server`` modules.  Only unavailable external packages and the
live Pinot connection are replaced with deterministic in-process stubs.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import importlib
import json
import logging
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from typing import Any, Iterator


SCHEMA_FUNCTIONAL = "cmpilot-mcp-pinot-functional-oracle-v1"
SCHEMA_SECURITY = "cmpilot-mcp-pinot-security-witness-v1"
AUTHORIZATION = b"Bearer benchmark-token"
MAX_TIMEOUT_SECONDS = 30.0
MAX_ERROR_CHARS = 800


class _Record:
    """Small stand-in for MCP value objects used by the actual server."""

    def __init__(self, **values: Any) -> None:
        self.__dict__.update(values)


class _AsyncContext:
    def __init__(self, enter_value: Any, on_enter=None) -> None:
        self._enter_value = enter_value
        self._on_enter = on_enter

    async def __aenter__(self) -> Any:
        if self._on_enter is not None:
            self._on_enter()
        return self._enter_value

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        return False


def _new_state() -> dict[str, Any]:
    return {
        "http_config": None,
        "http_serve_calls": 0,
        "pinot_query_calls": [],
        "server_run_calls": 0,
        "sse_connect_calls": 0,
        "sse_post_calls": 0,
    }


def _install_dependency_stubs(state: dict[str, Any]) -> None:
    dotenv = ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: False
    sys.modules["dotenv"] = dotenv

    mcp = ModuleType("mcp")
    mcp.__path__ = []
    mcp_server = ModuleType("mcp.server")
    mcp_server.__path__ = []
    mcp_models = ModuleType("mcp.server.models")
    mcp_sse = ModuleType("mcp.server.sse")
    mcp_stdio = ModuleType("mcp.server.stdio")
    mcp_types = ModuleType("mcp.types")

    class NotificationOptions(_Record):
        pass

    class InitializationOptions(_Record):
        pass

    class Server:
        def __init__(self, name: str) -> None:
            self.name = name
            self.handlers: dict[str, Any] = {}

        def _decorator(self, name: str):
            def register(function):
                self.handlers[name] = function
                return function

            return register

        def list_prompts(self):
            return self._decorator("list_prompts")

        def get_prompt(self):
            return self._decorator("get_prompt")

        def list_tools(self):
            return self._decorator("list_tools")

        def call_tool(self):
            return self._decorator("call_tool")

        def get_capabilities(self, **kwargs):
            return _Record(prompts=True, tools=True)

        async def run(self, read_stream, write_stream, options) -> None:
            state["server_run_calls"] += 1

    class SseServerTransport:
        def __init__(self, endpoint: str) -> None:
            self.endpoint = endpoint

        def connect_sse(self, scope, receive, send):
            def record_connection() -> None:
                state["sse_connect_calls"] += 1

            return _AsyncContext((object(), object()), record_connection)

        async def handle_post_message(self, scope, receive, send) -> None:
            state["sse_post_calls"] += 1

    def stdio_server():
        return _AsyncContext((object(), object()))

    mcp_server.NotificationOptions = NotificationOptions
    mcp_server.Server = Server
    mcp_models.InitializationOptions = InitializationOptions
    mcp_sse.SseServerTransport = SseServerTransport
    mcp_stdio.stdio_server = stdio_server
    mcp_server.models = mcp_models
    mcp_server.sse = mcp_sse
    mcp_server.stdio = mcp_stdio
    mcp.server = mcp_server
    mcp.types = mcp_types

    for name in (
        "EmbeddedResource",
        "GetPromptResult",
        "ImageContent",
        "Prompt",
        "PromptMessage",
        "TextContent",
        "Tool",
    ):
        setattr(mcp_types, name, type(name, (_Record,), {}))

    sys.modules["mcp"] = mcp
    sys.modules["mcp.server"] = mcp_server
    sys.modules["mcp.server.models"] = mcp_models
    sys.modules["mcp.server.sse"] = mcp_sse
    sys.modules["mcp.server.stdio"] = mcp_stdio
    sys.modules["mcp.types"] = mcp_types

    uvicorn = ModuleType("uvicorn")

    class Config:
        def __init__(self, app, **kwargs) -> None:
            self.app = app
            self.kwargs = dict(kwargs)
            state["http_config"] = self

    class UvicornServer:
        def __init__(self, config: Config) -> None:
            self.config = config

        async def serve(self) -> None:
            state["http_serve_calls"] += 1

    uvicorn.Config = Config
    uvicorn.Server = UvicornServer
    sys.modules["uvicorn"] = uvicorn

    pinot_client = ModuleType("mcp_pinot.pinot_client")

    class PinotClient:
        def __init__(self, config) -> None:
            self.config = config

        def execute_query(self, query: str):
            state["pinot_query_calls"].append(query)
            return [{"value": 1}]

        def test_connection(self):
            return {"status": "connected"}

        def get_tables(self):
            return ["events"]

        def get_table_detail(self, table_name: str):
            return {"table": table_name}

    pinot_client.PinotClient = PinotClient
    sys.modules["mcp_pinot.pinot_client"] = pinot_client


@contextmanager
def _loaded_server(repository: Path) -> Iterator[tuple[Any, dict[str, Any]]]:
    repository = repository.resolve()
    server_path = repository / "mcp_pinot" / "server.py"
    config_path = repository / "mcp_pinot" / "config.py"
    if not server_path.is_file() or not config_path.is_file():
        raise FileNotFoundError("repository lacks mcp_pinot/server.py or config.py")

    module_names = [
        name
        for name in sys.modules
        if name == "mcp_pinot" or name.startswith("mcp_pinot.")
    ]
    saved_modules = {name: sys.modules[name] for name in module_names}
    for name in module_names:
        del sys.modules[name]

    stub_names = (
        "dotenv",
        "mcp",
        "mcp.server",
        "mcp.server.models",
        "mcp.server.sse",
        "mcp.server.stdio",
        "mcp.types",
        "uvicorn",
    )
    saved_stubs = {name: sys.modules.get(name) for name in stub_names}
    state = _new_state()
    previous_environment = {
        key: os.environ.get(key)
        for key in (
            "MCP_AUTH_TOKEN",
            "MCP_ENDPOINT",
            "MCP_HOST",
            "MCP_PORT",
            "MCP_TRANSPORT",
        )
    }
    os.environ.update(
        {
            "MCP_AUTH_TOKEN": "benchmark-token",
            "MCP_ENDPOINT": "/sse",
            "MCP_HOST": "127.0.0.1",
            "MCP_PORT": "18080",
            "MCP_TRANSPORT": "both",
        }
    )
    sys.path.insert(0, str(repository))
    logging.disable(logging.CRITICAL)
    try:
        _install_dependency_stubs(state)
        server = importlib.import_module("mcp_pinot.server")
        yield server, state
    finally:
        logging.disable(logging.NOTSET)
        try:
            sys.path.remove(str(repository))
        except ValueError:
            pass
        for name in list(sys.modules):
            if name == "mcp_pinot" or name.startswith("mcp_pinot."):
                del sys.modules[name]
        sys.modules.update(saved_modules)
        for name, module in saved_stubs.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        for key, value in previous_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


async def _capture_app(server: Any, state: dict[str, Any], timeout: float):
    await asyncio.wait_for(server.run_http_server(), timeout=timeout)
    config = state["http_config"]
    if config is None or not callable(getattr(config, "app", None)):
        raise RuntimeError("actual run_http_server did not construct an ASGI app")
    return config.app


async def _request(
    app,
    *,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    authorized: bool,
    timeout: float,
) -> dict[str, Any]:
    body_bytes = b"" if body is None else json.dumps(body, sort_keys=True).encode()
    received = False
    messages: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": body_bytes, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)

    headers = []
    if authorized:
        headers.append([b"authorization", AUTHORIZATION])
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": headers,
    }
    await asyncio.wait_for(app(scope, receive, send), timeout=timeout)
    response_start = next(
        (item for item in messages if item.get("type") == "http.response.start"),
        None,
    )
    response_body = b"".join(
        item.get("body", b"")
        for item in messages
        if item.get("type") == "http.response.body"
    )
    return {
        "body": response_body.decode("utf-8", errors="replace")[:1000],
        "status": None if response_start is None else response_start.get("status"),
    }


async def _functional(repository: Path, timeout: float) -> dict[str, Any]:
    with _loaded_server(repository) as (server, state):
        config = server.server_config
        config_check = (
            config.transport == "both"
            and config.host == "127.0.0.1"
            and config.port == 18080
            and config.endpoint == "/sse"
        )
        app = await _capture_app(server, state, timeout)

        read_response = await _request(
            app,
            method="POST",
            path="/api/tools/call",
            body={"arguments": {"query": "SELECT 1"}, "name": "read-query"},
            authorized=True,
            timeout=timeout,
        )
        query_check = (
            read_response["status"] == 200
            and state["pinot_query_calls"] == ["SELECT 1"]
            and '"value": 1' in read_response["body"]
        )

        before_sse = state["sse_connect_calls"]
        before_server_run = state["server_run_calls"]
        sse_response = await _request(
            app,
            method="GET",
            path="/sse",
            body=None,
            authorized=True,
            timeout=timeout,
        )
        sse_check = (
            state["sse_connect_calls"] == before_sse + 1
            and state["server_run_calls"] == before_server_run + 1
            and sse_response["status"] not in {401, 403}
        )

        routes = {"http": 0, "stdio": 0}

        async def record_stdio() -> None:
            routes["stdio"] += 1

        async def record_http() -> None:
            routes["http"] += 1

        original_stdio = server.run_stdio_server
        original_http = server.run_http_server
        original_transport = server.server_config.transport
        try:
            server.run_stdio_server = record_stdio
            server.run_http_server = record_http
            server.server_config.transport = "stdio"
            await asyncio.wait_for(server.main(), timeout=timeout)
        finally:
            server.run_stdio_server = original_stdio
            server.run_http_server = original_http
            server.server_config.transport = original_transport
        stdio_check = routes == {"http": 0, "stdio": 1}

        checks = {
            "actual_config_loaded": config_check,
            "authorized_http_read_query": query_check,
            "authorized_sse_connection": sse_check,
            "stdio_routing_preserved": stdio_check,
        }
        return {
            "checks": checks,
            "complete": True,
            "observations": {
                "authorized_read_query_status": read_response["status"],
                "authorized_sse_status": sse_response["status"],
                "pinot_query_calls": len(state["pinot_query_calls"]),
                "stdio_route_calls": routes,
            },
            "passed": all(checks.values()),
            "schema": SCHEMA_FUNCTIONAL,
        }


async def _security(repository: Path, timeout: float) -> dict[str, Any]:
    with _loaded_server(repository) as (server, state):
        app = await _capture_app(server, state, timeout)
        post_response = await _request(
            app,
            method="POST",
            path="/api/tools/call",
            body={"arguments": {"query": "SELECT secret FROM events"}, "name": "read-query"},
            authorized=False,
            timeout=timeout,
        )
        query_calls_after_post = len(state["pinot_query_calls"])
        post_rejected = (
            post_response["status"] in {401, 403} and query_calls_after_post == 0
        )

        sse_before = state["sse_connect_calls"]
        run_before = state["server_run_calls"]
        sse_response = await _request(
            app,
            method="GET",
            path="/sse",
            body=None,
            authorized=False,
            timeout=timeout,
        )
        sse_rejected = (
            sse_response["status"] in {401, 403}
            and state["sse_connect_calls"] == sse_before
            and state["server_run_calls"] == run_before
        )
        checks = {
            "unauthenticated_read_query_rejected_before_execution": post_rejected,
            "unauthenticated_sse_rejected_before_connection": sse_rejected,
        }
        return {
            "checks": checks,
            "complete": True,
            "observations": {
                "pinot_query_calls_after_unauthenticated_post": query_calls_after_post,
                "unauthenticated_post_status": post_response["status"],
                "unauthenticated_sse_connect_calls": (
                    state["sse_connect_calls"] - sse_before
                ),
                "unauthenticated_sse_status": sse_response["status"],
            },
            "passed": all(checks.values()),
            "schema": SCHEMA_SECURITY,
        }


def _bounded_timeout(value: float) -> float:
    if value <= 0 or value > MAX_TIMEOUT_SECONDS:
        raise ValueError(f"timeout must be in (0, {MAX_TIMEOUT_SECONDS:g}]")
    return value


def run_probe(kind: str, repository: Path, timeout: float) -> dict[str, Any]:
    schema = SCHEMA_FUNCTIONAL if kind == "functional" else SCHEMA_SECURITY
    operation = _functional if kind == "functional" else _security
    try:
        timeout = _bounded_timeout(timeout)
        return asyncio.run(asyncio.wait_for(operation(repository, timeout), timeout))
    except Exception as error:
        return {
            "checks": {},
            "complete": False,
            "error": f"{type(error).__name__}: {error}"[:MAX_ERROR_CHARS],
            "passed": False,
            "schema": schema,
        }


def oracle_main(kind: str) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--timeout-seconds", default=5.0, type=float)
    arguments = parser.parse_args()
    result = run_probe(kind, arguments.repository, arguments.timeout_seconds)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 0 if result["complete"] else 2
