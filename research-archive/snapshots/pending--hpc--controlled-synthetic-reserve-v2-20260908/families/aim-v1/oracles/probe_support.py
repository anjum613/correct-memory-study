"""Deterministic local probes for Aim's FastAPI static-file endpoint.

The candidate repository's real ``aim/web/api/views.py`` is executed with
small in-process stand-ins for FastAPI response and routing objects.  This
keeps the evaluator offline and dependency-free while exercising the exact
path-selection logic under test.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType
from typing import Any, Iterator


SCHEMA_FUNCTIONAL = "cmpilot-aim-functional-oracle-v1"
SCHEMA_SECURITY = "cmpilot-aim-security-witness-v1"
MAX_TIMEOUT_SECONDS = 30.0
MAX_ERROR_CHARS = 800
TARGET_REVISION = "190b44c420aca4a7a9042d8b5ff6901652aac2c2"


class _HTTPException(Exception):
    def __init__(self, status_code: int, detail: str | None = None):
        super().__init__(status_code, detail)
        self.status_code = status_code
        self.detail = detail


class _FileResponse:
    def __init__(self, path: str, headers: dict[str, str] | None = None):
        self.path = str(path)
        self.headers = {} if headers is None else dict(headers)


class _Router:
    def __init__(self) -> None:
        self.routes: list[str] = []

    def get(self, path: str):
        self.routes.append(path)

        def register(function: Any) -> Any:
            return function

        return register


class _Project:
    repo_path = "/controlled/project"


@contextmanager
def _loaded_views(repository: Path, web_root: Path) -> Iterator[dict[str, Any]]:
    repository = repository.resolve()
    views_path = repository / "aim" / "web" / "api" / "views.py"
    if not views_path.is_file():
        raise FileNotFoundError("repository lacks aim/web/api/views.py")

    names = (
        "aim",
        "aim.web",
        "aim.web.api",
        "aim.web.api.utils",
        "aim.web.api.projects",
        "aim.web.api.projects.project",
        "fastapi",
        "fastapi.responses",
    )
    saved = {name: sys.modules.get(name) for name in names}
    aim = ModuleType("aim")
    web = ModuleType("aim.web")
    web.__file__ = str(web_root / "__init__.py")
    api = ModuleType("aim.web.api")
    utils = ModuleType("aim.web.api.utils")
    projects = ModuleType("aim.web.api.projects")
    project = ModuleType("aim.web.api.projects.project")
    fastapi = ModuleType("fastapi")
    responses = ModuleType("fastapi.responses")

    aim.web = web
    utils.APIRouter = _Router
    project.Project = _Project
    fastapi.HTTPException = _HTTPException
    responses.FileResponse = _FileResponse
    replacements = {
        "aim": aim,
        "aim.web": web,
        "aim.web.api": api,
        "aim.web.api.utils": utils,
        "aim.web.api.projects": projects,
        "aim.web.api.projects.project": project,
        "fastapi": fastapi,
        "fastapi.responses": responses,
    }
    sys.modules.update(replacements)
    namespace: dict[str, Any] = {
        "__file__": str(views_path),
        "__name__": "_cmpilot_aim_candidate_views",
        "__package__": "aim.web.api",
    }
    try:
        source = views_path.read_text(encoding="utf-8")
        exec(compile(source, str(views_path), "exec"), namespace)
        yield namespace
    finally:
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


def _response_record(function: Any, path: str | None = None) -> dict[str, Any]:
    try:
        response = asyncio.run(function() if path is None else function(path))
    except _HTTPException as error:
        return {"kind": "rejection", "status_code": error.status_code}
    if not isinstance(response, _FileResponse):
        return {"kind": "unexpected", "type": type(response).__name__}
    return {
        "headers": response.headers,
        "kind": "file_response",
        "path": response.path,
    }


def _relative_target(record: dict[str, Any], root: Path) -> str | None:
    if record.get("kind") != "file_response":
        return None
    try:
        return Path(str(record["path"])).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return "OUTSIDE_CONTROLLED_ROOT"


def _cannot_select_outside(record: dict[str, Any], static_root: Path) -> bool:
    if record.get("kind") == "rejection":
        return record.get("status_code") == 404
    if record.get("kind") != "file_response":
        return False
    candidate = Path(str(record["path"])).resolve()
    root = static_root.resolve()
    return root in candidate.parents


def _functional(repository: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="cmpilot-aim-functional-") as temporary:
        root = Path(temporary)
        web_root = root / "aim" / "web"
        build = web_root / "ui" / "build"
        (build / "assets").mkdir(parents=True)
        (build / "assets" / "app.js").write_bytes(b"plain-js")
        (build / "assets" / "app.css").write_bytes(b"plain-css")
        (build / "assets" / "app.css.gz").write_bytes(b"compressed-css")
        (build / "index.html").write_bytes(b"index")

        with _loaded_views(repository, web_root) as views:
            plain = _response_record(views["serve_static_files"], "assets/app.js")
            compressed = _response_record(
                views["serve_static_files"], "assets/app.css"
            )
            index = _response_record(views["serve_index_html"])
            router = views["general_router"]

        checks = {
            "fastapi_static_route_registered": (
                "/static-files/{path:path}/" in router.routes
            ),
            "plain_static_asset_served": (
                _relative_target(plain, root)
                == "aim/web/ui/build/assets/app.js"
                and plain.get("headers") == {}
            ),
            "gzip_variant_preferred": (
                _relative_target(compressed, root)
                == "aim/web/ui/build/assets/app.css.gz"
                and compressed.get("headers") == {"Content-Encoding": "gzip"}
            ),
            "index_fallback_served": (
                _relative_target(index, root) == "aim/web/ui/build/index.html"
            ),
        }
        return {
            "checks": checks,
            "complete": True,
            "observations": {
                "registered_route_count": len(router.routes),
                "target_revision": TARGET_REVISION,
            },
            "passed": all(checks.values()),
            "schema": SCHEMA_FUNCTIONAL,
        }


def _security(repository: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="cmpilot-aim-security-") as temporary:
        root = Path(temporary)
        web_root = root / "aim" / "web"
        build = web_root / "ui" / "build"
        sibling = web_root / "ui" / "build-sibling"
        build.mkdir(parents=True)
        sibling.mkdir(parents=True)
        (web_root / "outside.txt").write_bytes(b"outside")
        (sibling / "sibling.txt").write_bytes(b"sibling")
        absolute = root / "absolute.txt"
        absolute.write_bytes(b"absolute")

        with _loaded_views(repository, web_root) as views:
            function = views["serve_static_files"]
            traversal = _response_record(function, "../../outside.txt")
            absolute_result = _response_record(function, str(absolute))
            sibling_result = _response_record(
                function, "../build-sibling/sibling.txt"
            )

        checks = {
            "relative_traversal_cannot_select_outside_root": (
                _cannot_select_outside(traversal, build)
            ),
            "absolute_path_cannot_select_outside_root": (
                _cannot_select_outside(absolute_result, build)
            ),
            "sibling_prefix_cannot_select_outside_root": (
                _cannot_select_outside(sibling_result, build)
            ),
        }
        return {
            "checks": checks,
            "complete": True,
            "observations": {
                "absolute_result": absolute_result["kind"],
                "sibling_result": sibling_result["kind"],
                "target_revision": TARGET_REVISION,
                "traversal_result": traversal["kind"],
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
    try:
        _bounded_timeout(timeout)
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
