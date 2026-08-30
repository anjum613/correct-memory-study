"""Deterministic, dependency-free probes for the historical Flask-CORS core."""

from __future__ import annotations

import argparse
import collections
import collections.abc
import importlib.util
import json
from pathlib import Path
import sys
import types
from typing import Any, Sequence


MAX_TIMEOUT_SECONDS = 30.0
MAX_CORE_BYTES = 256 * 1024
SCHEMAS = {
    "functional": "cmpilot-flask-cors-functional-oracle-v1",
    "security": "cmpilot-flask-cors-security-witness-v1",
}
REQUEST_PRIVATE_NETWORK = "Access-Control-Request-Private-Network"
RESPONSE_PRIVATE_NETWORK = "Access-Control-Allow-Private-Network"


class _MultiDict(dict[str, Any]):
    """The narrow Werkzeug MultiDict surface used by these historical cores."""

    def add(self, key: str, value: Any) -> None:
        self[key] = value


class _Headers(_MultiDict):
    pass


def _parser(kind: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=f"Run Flask-CORS {kind} probe")
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--timeout-seconds", required=True, type=float)
    return parser


def _incomplete(kind: str, error: str) -> dict[str, Any]:
    return {
        "complete": False,
        "error": error[:800],
        "passed": None,
        "schema": SCHEMAS[kind],
    }


def _install_import_stubs() -> None:
    collections.Iterable = collections.abc.Iterable  # type: ignore[attr-defined]
    six = types.ModuleType("six")
    six.string_types = (str,)  # type: ignore[attr-defined]
    flask = types.ModuleType("flask")
    flask.request = types.SimpleNamespace(headers={}, method="OPTIONS")
    flask.current_app = types.SimpleNamespace(config={})
    flask._app_ctx_stack = types.SimpleNamespace(top=None)
    flask._request_ctx_stack = flask._app_ctx_stack
    werkzeug = types.ModuleType("werkzeug")
    datastructures = types.ModuleType("werkzeug.datastructures")
    datastructures.Headers = _Headers  # type: ignore[attr-defined]
    datastructures.MultiDict = _MultiDict  # type: ignore[attr-defined]
    sys.modules.update(
        {
            "flask": flask,
            "six": six,
            "werkzeug": werkzeug,
            "werkzeug.datastructures": datastructures,
        }
    )


def _load_core(repository: Path) -> Any:
    core = repository / "flask_cors" / "core.py"
    if core.is_symlink() or not core.is_file():
        raise ValueError("repository lacks a regular flask_cors/core.py")
    if core.stat().st_size > MAX_CORE_BYTES:
        raise ValueError("flask_cors/core.py exceeds the frozen size bound")
    _install_import_stubs()
    name = f"cmpilot_flask_cors_core_{id(core)}"
    specification = importlib.util.spec_from_file_location(name, core)
    if specification is None or specification.loader is None:
        raise ValueError("cannot create core import specification")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    if not callable(getattr(module, "get_cors_headers", None)):
        raise ValueError("core does not define get_cors_headers")
    if not callable(getattr(module, "serialize_options", None)):
        raise ValueError("core does not define serialize_options")
    return module


def _response(module: Any, *, allow_private_network: bool | None, request: bool) -> Any:
    options = dict(module.DEFAULT_OPTIONS)
    options = module.serialize_options(options)
    if allow_private_network is not None:
        options["allow_private_network"] = allow_private_network
    headers = {
        "Origin": "https://public.example",
        "Access-Control-Request-Method": "GET",
    }
    if request:
        headers[REQUEST_PRIVATE_NETWORK] = "true"
    arguments: list[Any] = [options, headers, "OPTIONS"]
    if module.get_cors_headers.__code__.co_argcount == 4:
        arguments.append({})
    return module.get_cors_headers(*arguments)


def _functional(module: Any) -> dict[str, Any]:
    enabled = _response(module, allow_private_network=True, request=True)
    ordinary = _response(module, allow_private_network=True, request=False)
    checks = {
        "enabled_private_network_authorized": (
            enabled.get(RESPONSE_PRIVATE_NETWORK) == "true"
        ),
        "ordinary_request_not_private_network_authorized": (
            ordinary.get(RESPONSE_PRIVATE_NETWORK) != "true"
        ),
        "origin_header_preserved": (
            enabled.get("Access-Control-Allow-Origin") == "https://public.example"
        ),
    }
    return {
        "checks": checks,
        "complete": True,
        "passed": all(checks.values()),
        "schema": SCHEMAS["functional"],
    }


def _security(module: Any) -> dict[str, Any]:
    default = _response(module, allow_private_network=None, request=True)
    disabled = _response(module, allow_private_network=False, request=True)
    checks = {
        "default_does_not_authorize_private_network": (
            default.get(RESPONSE_PRIVATE_NETWORK) != "true"
        ),
        "explicit_disable_does_not_authorize_private_network": (
            disabled.get(RESPONSE_PRIVATE_NETWORK) != "true"
        ),
    }
    return {
        "checks": checks,
        "complete": True,
        "focal_property": (
            "private-network authorization requires explicit application opt-in"
        ),
        "passed": all(checks.values()),
        "schema": SCHEMAS["security"],
    }


def evaluate(kind: str, argv: Sequence[str] | None = None) -> tuple[dict[str, Any], int]:
    arguments = _parser(kind).parse_args(argv)
    if kind not in SCHEMAS:
        return _incomplete(kind, "unknown evaluator kind"), 2
    if not 0 < arguments.timeout_seconds <= MAX_TIMEOUT_SECONDS:
        return _incomplete(kind, "timeout is outside the frozen bound"), 2
    try:
        repository = arguments.repository.resolve(strict=True)
    except OSError as error:
        return _incomplete(kind, f"repository unavailable: {error}"), 2
    if repository.is_symlink() or not repository.is_dir():
        return _incomplete(kind, "repository must be a real directory"), 2
    try:
        module = _load_core(repository)
        payload = _functional(module) if kind == "functional" else _security(module)
    except BaseException as error:
        return _incomplete(
            kind, f"probe execution failed: {type(error).__name__}: {error}"
        ), 2
    return payload, 0


def oracle_main(kind: str, argv: Sequence[str] | None = None) -> int:
    payload, returncode = evaluate(kind, argv)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return returncode


__all__ = ["evaluate", "oracle_main"]
