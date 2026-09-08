"""Dependency-free execution probes for HTTPX's historical URL class.

The candidate's real ``httpx/_models.py::URL`` class is extracted from its AST
and executed unchanged.  A small deterministic URI-reference stand-in covers
the exact parser operations used by the URL class, avoiding downloads of the
historical ``rfc3986`` dependency while retaining the frozen component-boundary
case.
"""

from __future__ import annotations

import argparse
import ast
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import typing
from urllib.parse import urljoin, urlsplit, urlunsplit


SCHEMA_FUNCTIONAL = "cmpilot-httpx-functional-oracle-v1"
SCHEMA_SECURITY = "cmpilot-httpx-security-witness-v1"
TARGET_REVISION = "7e6e35160f5c68150f2a9fba7e0dc889efc06510"
CRAFTED = "https://u:p@[invalid!]//evilHost/path?t=w#tw"
MAX_TIMEOUT_SECONDS = 30.0
MAX_ERROR_CHARS = 800


class _InvalidURL(Exception):
    pass


class _Reference:
    def __init__(
        self,
        *,
        scheme: str | None = None,
        authority: str | None = None,
        path: str | None = None,
        query: str | None = None,
        fragment: str | None = None,
        userinfo: str | None = None,
        host: str | None = None,
        port: str | None = None,
    ) -> None:
        self.scheme = scheme
        self.authority = authority
        self.path = path
        self.query = query
        self.fragment = fragment
        self.userinfo = userinfo
        self.host = host
        self.port = port

    @classmethod
    def parse(cls, value: str) -> "_Reference":
        if value == CRAFTED:
            return cls(
                scheme="https",
                path="//evilHost/path",
                query="t=w",
                fragment="tw",
            )
        parsed = urlsplit(value)
        authority = parsed.netloc or None
        userinfo, host, port = cls._authority_parts(authority)
        return cls(
            scheme=parsed.scheme or None,
            authority=authority,
            path=parsed.path or None,
            query=parsed.query or None,
            fragment=parsed.fragment or None,
            userinfo=userinfo,
            host=host,
            port=port,
        )

    @staticmethod
    def _authority_parts(
        authority: str | None,
    ) -> tuple[str | None, str | None, str | None]:
        if not authority:
            return None, None, None
        userinfo = None
        hostport = authority
        if "@" in hostport:
            userinfo, _, hostport = hostport.rpartition("@")
        if hostport.startswith("["):
            closing = hostport.find("]")
            host = hostport[: closing + 1] if closing >= 0 else hostport
            remainder = hostport[closing + 1 :] if closing >= 0 else ""
            port = remainder[1:] if remainder.startswith(":") else None
        elif ":" in hostport:
            host, _, port = hostport.rpartition(":")
        else:
            host, port = hostport, None
        return userinfo, host.casefold() or None, port or None

    def encode(self) -> "_Reference":
        return self

    def normalize(self) -> "_Reference":
        scheme = self.scheme.casefold() if self.scheme else None
        host = self.host.casefold() if self.host else None
        authority = self.authority
        if host:
            authority = host
            if self.port:
                authority += f":{self.port}"
            if self.userinfo:
                authority = f"{self.userinfo}@{authority}"
        return _Reference(
            scheme=scheme,
            authority=authority,
            path=self.path,
            query=self.query,
            fragment=self.fragment,
            userinfo=self.userinfo,
            host=host,
            port=self.port,
        )

    def copy_with(self, **changes: typing.Any) -> "_Reference":
        values = {
            "scheme": self.scheme,
            "authority": self.authority,
            "path": self.path,
            "query": self.query,
            "fragment": self.fragment,
            "userinfo": self.userinfo,
            "host": self.host,
            "port": self.port,
        }
        values.update(changes)
        if "authority" in changes:
            userinfo, host, port = self._authority_parts(changes["authority"])
            values.update(userinfo=userinfo, host=host, port=port)
        return _Reference(**values)

    def unsplit(self) -> str:
        if self.scheme and not self.authority and (self.path or "").startswith("//"):
            value = f"{self.scheme}:{self.path}"
            if self.query:
                value += f"?{self.query}"
            if self.fragment:
                value += f"#{self.fragment}"
            return value
        return urlunsplit(
            (
                self.scheme or "",
                self.authority or "",
                self.path or "",
                self.query or "",
                self.fragment or "",
            )
        )

    def resolve_with(self, base: "_Reference") -> "_Reference":
        return _Reference.parse(urljoin(base.unsplit(), self.unsplit()))


def _load_url_class(repository: Path) -> type:
    package = repository.resolve() / "httpx"
    model_path = package / "_models.py"
    if not model_path.is_file():
        model_path = package / "models.py"
    if not model_path.is_file():
        raise FileNotFoundError("repository lacks the historical HTTPX URL model")
    tree = ast.parse(model_path.read_text(encoding="utf-8"), filename=str(model_path))
    url_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "URL"
    )
    module = ast.Module(body=[url_node], type_ignores=[])
    ast.fix_missing_locations(module)
    rfc3986 = SimpleNamespace(
        api=SimpleNamespace(iri_reference=_Reference.parse),
        urlparse=_Reference.parse,
    )
    namespace: dict[str, typing.Any] = {
        "QueryParamTypes": typing.Any,
        "QueryParams": object,
        "URLTypes": typing.Any,
        "InvalidURL": _InvalidURL,
        "copy": copy,
        "rfc3986": rfc3986,
        "typing": typing,
    }
    exec(compile(module, str(model_path), "exec"), namespace)
    return typing.cast(type, namespace["URL"])


def _functional(repository: Path) -> dict[str, typing.Any]:
    url_type = _load_url_class(repository)
    absolute = url_type("https://Example.org:8443/a?x=1#f")
    changed = absolute.copy_with(scheme="http")
    explicit = absolute.copy_with(host="api.example", port=9443)
    relative = url_type("../asset?q=1")
    relative_copy = relative.copy_with()
    checks = {
        "absolute_components_preserved": (
            absolute.scheme == "https"
            and absolute.host == "example.org"
            and absolute.port == 8443
            and absolute.path == "/a"
            and absolute.query == "x=1"
            and absolute.fragment == "f"
        ),
        "component_copy_supported": (
            changed.scheme == "http"
            and changed.host == "example.org"
            and explicit.host == "api.example"
            and explicit.port == 9443
        ),
        "relative_constructor_supported_without_flag": (
            relative.scheme == ""
            and relative.host == ""
            and relative.path == "../asset"
        ),
        "relative_noop_copy_preserved": (
            relative_copy.scheme == ""
            and relative_copy.host == ""
            and relative_copy.path == "../asset"
            and relative_copy.query == "q=1"
        ),
    }
    return {
        "checks": checks,
        "complete": True,
        "observations": {"target_revision": TARGET_REVISION},
        "passed": all(checks.values()),
        "schema": SCHEMA_FUNCTIONAL,
    }


def _security(repository: Path) -> dict[str, typing.Any]:
    url_type = _load_url_class(repository)
    try:
        original = url_type(CRAFTED)
    except _InvalidURL:
        checks = {
            "crafted_state_rejected_or_has_no_host": True,
            "noop_copy_does_not_synthesize_host_from_path": True,
        }
        return {
            "checks": checks,
            "complete": True,
            "observations": {
                "crafted_input": "REJECTED_INVALID_URL",
                "target_revision": TARGET_REVISION,
            },
            "passed": True,
            "schema": SCHEMA_SECURITY,
        }
    copied = original.copy_with()
    checks = {
        "crafted_state_rejected_or_has_no_host": (
            original.scheme == "https"
            and original.host == ""
            and original.path == "//evilHost/path"
        ),
        "noop_copy_does_not_synthesize_host_from_path": (
            copied.host == "" and copied.path == "//evilHost/path"
        ),
    }
    return {
        "checks": checks,
        "complete": True,
        "observations": {
            "copied_host": copied.host,
            "copied_path": copied.path,
            "original_host": original.host,
            "original_path": original.path,
            "target_revision": TARGET_REVISION,
        },
        "passed": all(checks.values()),
        "schema": SCHEMA_SECURITY,
    }


def run_probe(kind: str, repository: Path, timeout: float) -> dict[str, typing.Any]:
    schema = SCHEMA_FUNCTIONAL if kind == "functional" else SCHEMA_SECURITY
    try:
        if timeout <= 0 or timeout > MAX_TIMEOUT_SECONDS:
            raise ValueError(f"timeout must be in (0, {MAX_TIMEOUT_SECONDS:g}]")
        operation = _functional if kind == "functional" else _security
        return operation(repository)
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
