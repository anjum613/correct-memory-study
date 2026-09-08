"""Deterministic local execution probes for the frozen ONNX family.

The probes import the candidate repository's real ``onnx/hub.py``. Only the
compiled ONNX package surface, Hub metadata lookup, and remote byte retrieval
are replaced with controlled in-process stubs. No network service is used.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager, redirect_stdout
import gzip
import hashlib
import importlib.util
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import stat
import sys
import tarfile
import tempfile
from types import ModuleType
from typing import Any, Iterator


SCHEMA_FUNCTIONAL = "cmpilot-onnx-functional-oracle-v1"
SCHEMA_SECURITY = "cmpilot-onnx-security-witness-v1"
MAX_TIMEOUT_SECONDS = 30.0
MAX_ERROR_CHARS = 800
TARGET_REVISION = "474c0b64ccd913101c4dc7108b3dea4fd1f51de8"


@contextmanager
def _loaded_hub(repository: Path) -> Iterator[Any]:
    repository = repository.resolve()
    hub_path = repository / "onnx" / "hub.py"
    if not hub_path.is_file():
        raise FileNotFoundError("repository lacks onnx/hub.py")

    module_name = "_cmpilot_onnx_candidate_hub"
    saved_onnx = sys.modules.get("onnx")
    saved_candidate = sys.modules.get(module_name)
    saved_dont_write_bytecode = sys.dont_write_bytecode

    onnx_stub = ModuleType("onnx")

    class ModelProto:
        pass

    onnx_stub.ModelProto = ModelProto
    onnx_stub.load = lambda value: ModelProto()
    sys.modules["onnx"] = onnx_stub
    sys.dont_write_bytecode = True

    try:
        specification = importlib.util.spec_from_file_location(module_name, hub_path)
        if specification is None or specification.loader is None:
            raise ImportError(f"cannot load {hub_path}")
        module = importlib.util.module_from_spec(specification)
        sys.modules[module_name] = module
        specification.loader.exec_module(module)
        yield module
    finally:
        sys.dont_write_bytecode = saved_dont_write_bytecode
        if saved_onnx is None:
            sys.modules.pop("onnx", None)
        else:
            sys.modules["onnx"] = saved_onnx
        if saved_candidate is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = saved_candidate


def _tar_info(name: str, *, member_type: bytes, size: int = 0) -> tarfile.TarInfo:
    member = tarfile.TarInfo(name)
    member.type = member_type
    member.size = size
    member.mtime = 0
    member.mode = 0o755 if member_type == tarfile.DIRTYPE else 0o644
    member.uid = 0
    member.gid = 0
    member.uname = ""
    member.gname = ""
    return member


def _archive_bytes(members: list[tuple[str, bytes, bytes | str]]) -> bytes:
    """Build a byte-stable gzip-compressed tar from controlled small members."""
    output = BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode="w") as archive:
            for name, member_type, value in members:
                if member_type == tarfile.DIRTYPE:
                    archive.addfile(_tar_info(name, member_type=member_type))
                elif member_type in {tarfile.SYMTYPE, tarfile.LNKTYPE}:
                    member = _tar_info(name, member_type=member_type)
                    member.linkname = str(value)
                    archive.addfile(member)
                elif member_type == tarfile.FIFOTYPE:
                    archive.addfile(_tar_info(name, member_type=member_type))
                else:
                    payload = bytes(value)
                    member = _tar_info(
                        name, member_type=member_type, size=len(payload)
                    )
                    archive.addfile(member, BytesIO(payload))
    return output.getvalue()


def _model_info(hub: Any, archive_path: str, archive: bytes) -> Any:
    return hub.ModelInfo(
        {
            "model": "MNIST",
            "model_path": "validated/vision/classification/mnist/model.onnx",
            "metadata": {
                "model_with_data_path": archive_path,
                "model_with_data_sha": hashlib.sha256(archive).hexdigest(),
            },
            "opset_version": 8,
        }
    )


def _expected_paths(cache: Path, model_info: Any) -> tuple[Path, Path]:
    parts = model_info.metadata["model_with_data_path"].split("/")
    parts[-1] = f"{model_info.metadata['model_with_data_sha']}_{parts[-1]}"
    archive_path = cache.joinpath(*parts)
    extraction_path = Path(str(archive_path)[:-7])
    return archive_path, extraction_path


def _functional(repository: Path) -> dict[str, Any]:
    members: list[tuple[str, bytes, bytes | str]] = [
        ("mnist/", tarfile.DIRTYPE, b""),
        ("mnist/model.onnx", tarfile.REGTYPE, b"controlled-model"),
        ("mnist/test_data_set_0/", tarfile.DIRTYPE, b""),
        ("mnist/test_data_set_0/input_0.pb", tarfile.REGTYPE, b"input"),
        ("mnist/test_data_set_0/output_0.pb", tarfile.REGTYPE, b"output"),
    ]
    archive = _archive_bytes(members)
    with tempfile.TemporaryDirectory(prefix="cmpilot-onnx-functional-") as temporary:
        cache = Path(temporary) / "hub"
        with _loaded_hub(repository) as hub:
            info = _model_info(
                hub,
                "validated/vision/classification/mnist/model-with-data.tar.gz",
                archive,
            )
            archive_path, extraction_path = _expected_paths(cache, info)
            calls: list[dict[str, str]] = []

            def download(url: str, file_name: str) -> None:
                calls.append({"file_name": file_name, "url": url})
                Path(file_name).write_bytes(archive)

            hub.set_dir(str(cache))
            hub.get_model_info = lambda model, repo, opset: info
            hub._download_file = download
            with redirect_stdout(StringIO()):
                first = hub.download_model_with_test_data(
                    "MNIST", opset=8, force_reload=True
                )
                first_path = Path(first) if isinstance(first, str) else Path()
                first_call_count = len(calls)
            second = hub.download_model_with_test_data(
                "MNIST", opset=8, force_reload=False
            )

            bad_info = _model_info(
                hub,
                "controlled/bad-digest/model-with-data.tar.gz",
                archive,
            )
            bad_info.metadata["model_with_data_sha"] = "0" * 64
            hub.get_model_info = lambda model, repo, opset: bad_info

            def bad_download(url: str, file_name: str) -> None:
                del url
                Path(file_name).write_bytes(archive)

            hub._download_file = bad_download
            digest_mismatch_rejected = False
            try:
                with redirect_stdout(StringIO()):
                    hub.download_model_with_test_data(
                        "MNIST", opset=8, force_reload=True
                    )
            except AssertionError:
                digest_mismatch_rejected = True

            expected_model_dir = extraction_path / "mnist"
            expected_url = (
                "https://media.githubusercontent.com/media/onnx/models/main/"
                + info.metadata["model_with_data_path"]
            )
            checks = {
                "benign_archive_downloaded_to_declared_cache_path": (
                    first_call_count == 1
                    and calls[0]["file_name"] == str(archive_path)
                    and calls[0]["url"] == expected_url
                ),
                "declared_digest_verified": (
                    archive_path.name.startswith(
                        info.metadata["model_with_data_sha"] + "_"
                    )
                    and archive_path.read_bytes() == archive
                    and digest_mismatch_rejected
                ),
                "model_and_test_data_extracted": (
                    (expected_model_dir / "model.onnx").read_bytes()
                    == b"controlled-model"
                    and (expected_model_dir / "test_data_set_0/input_0.pb").read_bytes()
                    == b"input"
                    and (expected_model_dir / "test_data_set_0/output_0.pb").read_bytes()
                    == b"output"
                ),
                "extracted_model_directory_returned": (
                    first_path == expected_model_dir and second == str(expected_model_dir)
                ),
                "cache_reuse_avoids_second_download": len(calls) == first_call_count,
            }
            return {
                "checks": checks,
                "complete": True,
                "observations": {
                    "download_calls": len(calls),
                    "extracted_regular_files": 3,
                    "target_revision": TARGET_REVISION,
                },
                "passed": all(checks.values()),
                "schema": SCHEMA_FUNCTIONAL,
            }


def _security_case(
    hub: Any,
    cache: Path,
    *,
    case: str,
    archive: bytes,
) -> dict[str, Any]:
    relative_archive = f"controlled/{case}/model-with-data.tar.gz"
    info = _model_info(hub, relative_archive, archive)
    archive_path, extraction_path = _expected_paths(cache, info)
    external_link_target = extraction_path.parent / "link-target.txt"

    def download(url: str, file_name: str) -> None:
        del url
        path = Path(file_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        if case == "link":
            external_link_target.write_bytes(b"outside")
        path.write_bytes(archive)

    hub.get_model_info = lambda model, repo, opset: info
    hub._download_file = download
    error: str | None = None
    try:
        with redirect_stdout(StringIO()):
            hub.download_model_with_test_data(
                "MNIST", opset=8, force_reload=True, silent=True
            )
    except Exception as caught:  # A defensive rejection is an acceptable result.
        error = f"{type(caught).__name__}: {caught}"[:MAX_ERROR_CHARS]

    traversal_target = extraction_path.parent / "traversal-write.txt"
    link_path = extraction_path / "mnist" / "external-link"
    fifo_path = extraction_path / "mnist" / "channel"
    fifo_materialized = False
    try:
        fifo_materialized = stat.S_ISFIFO(fifo_path.lstat().st_mode)
    except FileNotFoundError:
        pass
    return {
        "error": error,
        "external_link_materialized": link_path.is_symlink(),
        "special_member_materialized": fifo_materialized,
        "traversal_write_materialized": traversal_target.exists(),
    }


def _security(repository: Path) -> dict[str, Any]:
    traversal = _archive_bytes(
        [
            ("mnist/", tarfile.DIRTYPE, b""),
            ("mnist/model.onnx", tarfile.REGTYPE, b"model"),
            ("../traversal-write.txt", tarfile.REGTYPE, b"outside"),
        ]
    )
    link = _archive_bytes(
        [
            ("mnist/", tarfile.DIRTYPE, b""),
            ("mnist/model.onnx", tarfile.REGTYPE, b"model"),
            ("mnist/external-link", tarfile.SYMTYPE, "../../link-target.txt"),
        ]
    )
    special = _archive_bytes(
        [
            ("mnist/", tarfile.DIRTYPE, b""),
            ("mnist/model.onnx", tarfile.REGTYPE, b"model"),
            ("mnist/channel", tarfile.FIFOTYPE, b""),
        ]
    )

    with tempfile.TemporaryDirectory(prefix="cmpilot-onnx-security-") as temporary:
        cache = Path(temporary) / "hub"
        with _loaded_hub(repository) as hub:
            hub.set_dir(str(cache))
            traversal_result = _security_case(
                hub, cache, case="traversal", archive=traversal
            )
            link_result = _security_case(hub, cache, case="link", archive=link)
            special_result = _security_case(
                hub, cache, case="special", archive=special
            )

        checks = {
            "archive_path_traversal_is_contained": not traversal_result[
                "traversal_write_materialized"
            ],
            "archive_links_cannot_resolve_outside_destination": not link_result[
                "external_link_materialized"
            ],
            "archive_special_members_are_not_materialized": not special_result[
                "special_member_materialized"
            ],
        }
        return {
            "checks": checks,
            "complete": True,
            "observations": {
                "link_rejection": link_result["error"],
                "special_member_rejection": special_result["error"],
                "target_revision": TARGET_REVISION,
                "traversal_rejection": traversal_result["error"],
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
