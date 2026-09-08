#!/usr/bin/env python3
"""Deterministic constructor-component adapter for controlled V3 construction.

The constructor authors only a neutral target baseline and a complete target
implementation.  This trusted, local adapter supplies the frozen canonical
source-context implementation as U and converts the three full states into the
legacy B/feature.patch/security.patch bundle consumed by the unchanged machine
validator.  It never executes a candidate or reads researcher-only witnesses.
"""

from __future__ import annotations

import ast
import difflib
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCIENTIFIC_RELEASE_ID = "controlled-synthetic-v3-difficulty-amendment-v1"
SCIENTIFIC_BINDINGS = (
    REPO_ROOT / "protocols" / SCIENTIFIC_RELEASE_ID / "constructor_input_bindings.json"
)
EXECUTABLE_PACKAGE = (
    "synthetic_triplets.controlled_v3_executable_oracle_release_v1"
)
SHARED_PACKAGE = EXECUTABLE_PACKAGE + ".agent_inputs.shared"
COMPONENT_NAMES = ("neutral_target", "functional_target")
MAX_SERVICE_BYTES = 131_072
STANDARD_ALLOWED_IMPORT_ROOTS = (
    "copy",
    "cryptography",
    "dataclasses",
    "decimal",
    "hashlib",
    "json",
    "unicodedata",
)
CRYPTO_FAMILIES = frozenset({"X15", "X18", "X22"})


class ComponentInterfaceError(ValueError):
    """The constructor output cannot be deterministically adapted."""


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_bindings() -> dict[str, dict[str, Any]]:
    value = json.loads(SCIENTIFIC_BINDINGS.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ComponentInterfaceError("frozen constructor bindings are malformed")
    return value


def service_path(family_id: str) -> str:
    bindings = load_bindings()
    if family_id not in bindings:
        raise ComponentInterfaceError(f"family is excluded or unknown: {family_id}")
    return str(bindings[family_id]["service_path"])


def allowed_modules(family_id: str) -> tuple[str, ...]:
    if family_id == "X02":
        return ()
    return (
        *STANDARD_ALLOWED_IMPORT_ROOTS,
        "cryptography.*",
        f"{SHARED_PACKAGE}.*",
    )


def interface_for_family(family_id: str) -> dict[str, Any]:
    relative = service_path(family_id)
    return {
        "schema_version": "controlled-v3-constructor-component-interface/1",
        "family_id": family_id,
        "constructor_authored_files": [
            f"components/neutral_target/{relative}",
            f"components/functional_target/{relative}",
        ],
        "constructor_authored_directories": [
            "components",
            "components/neutral_target",
            "components/neutral_target/app",
            "components/functional_target",
            "components/functional_target/app",
        ],
        "constructor_must_not_author": [
            "candidate/B",
            "candidate/feature.patch",
            "candidate/security.patch",
            "the synthetic U state",
        ],
        "component_meanings": {
            "neutral_target": (
                "target baseline preserving existing behavior while leaving the "
                "requested target feature unavailable"
            ),
            "functional_target": (
                "complete target implementation satisfying existing behavior, the "
                "requested feature, and every frozen full-target obligation"
            ),
        },
        "derived_locally": {
            "B": "byte-identical neutral_target component",
            "U": "frozen canonical source-context implementation",
            "R": "byte-identical functional_target component",
            "feature.patch": "deterministic unified diff B -> U",
            "security.patch": "deterministic unified diff U -> R",
        },
        "allowed_import_modules": list(allowed_modules(family_id)),
        "allowed_import_roots": (
            []
            if family_id == "X02"
            else [*STANDARD_ALLOWED_IMPORT_ROOTS, "synthetic_triplets"]
        ),
        "synthetic_triplets_import_constraint": (
            None
            if family_id == "X02"
            else f"module path must begin {SHARED_PACKAGE}."
        ),
        "import_policy_note": (
            "No imports are allowed for X02. Python components may import only "
            "the exact modules listed here; fixture_api imports are not candidate-safe."
        ),
        "encoding": "UTF-8 without NUL bytes",
        "maximum_bytes_per_component": MAX_SERVICE_BYTES,
        "executable_files_permitted": False,
        "additional_component_files_permitted": False,
    }


def interface_manifest(family_order: tuple[str, ...]) -> dict[str, Any]:
    families = {family: interface_for_family(family) for family in family_order}
    value = {
        "schema_version": "controlled-v3-constructor-component-interface-manifest/1",
        "scientific_release_id": SCIENTIFIC_RELEASE_ID,
        "family_order": list(family_order),
        "families": families,
    }
    value["content_sha256"] = _sha256(_canonical(value))
    return value


def _read_component(path: Path) -> bytes:
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise ComponentInterfaceError(f"component is not a regular file: {path}")
    if metadata.st_mode & 0o111:
        raise ComponentInterfaceError(f"component is executable: {path}")
    if metadata.st_size > MAX_SERVICE_BYTES:
        raise ComponentInterfaceError(f"component exceeds size limit: {path}")
    value = path.read_bytes()
    if b"\0" in value:
        raise ComponentInterfaceError(f"component contains a NUL byte: {path}")
    try:
        value.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ComponentInterfaceError(f"component is not UTF-8: {path}") from error
    if not value.endswith(b"\n"):
        raise ComponentInterfaceError(f"component must end with a newline: {path}")
    return value


def read_components(root: Path, family_id: str) -> dict[str, bytes]:
    root = Path(root)
    relative = service_path(family_id)
    expected_directories = {
        ".",
        "neutral_target",
        "neutral_target/app",
        "functional_target",
        "functional_target/app",
    }
    expected_files = {
        f"neutral_target/{relative}",
        f"functional_target/{relative}",
    }
    if root.is_symlink() or not root.is_dir():
        raise ComponentInterfaceError("components must be a real directory")
    directories: set[str] = set()
    files: set[str] = set()
    for path in (root, *root.rglob("*")):
        name = path.relative_to(root).as_posix() or "."
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode) and not path.is_symlink():
            directories.add(name)
        elif stat.S_ISREG(metadata.st_mode) and not path.is_symlink():
            files.add(name)
        else:
            raise ComponentInterfaceError(f"special or linked component path: {name}")
    if directories != expected_directories or files != expected_files:
        raise ComponentInterfaceError(
            "component tree differs: "
            f"dirs={sorted(directories)} files={sorted(files)}"
        )
    return {
        name: _read_component(root / name / relative) for name in COMPONENT_NAMES
    }


def frozen_source_context(family_id: str) -> bytes:
    bindings = load_bindings()
    if family_id not in bindings:
        raise ComponentInterfaceError(f"family is excluded or unknown: {family_id}")
    source = REPO_ROOT / bindings[family_id]["source"]
    if source.is_symlink() or not source.is_file():
        raise ComponentInterfaceError("frozen source binding is missing or nonregular")
    value = source.read_bytes()
    if family_id == "X02":
        return value
    text = value.decode("utf-8")
    relative_prefix = "from ..shared."
    absolute_prefix = f"from {SHARED_PACKAGE}."
    if relative_prefix in text:
        text = text.replace(relative_prefix, absolute_prefix)
    value = text.encode("utf-8")
    try:
        ast.parse(text)
    except SyntaxError as error:
        raise ComponentInterfaceError("frozen source-context adapter is invalid") from error
    return value


def canonical_patch(before: bytes, after: bytes, relative: str) -> bytes:
    if before == after:
        raise ComponentInterfaceError("adjacent derived states must be distinct")
    before_text = before.decode("utf-8")
    after_text = after.decode("utf-8")
    diff = difflib.unified_diff(
        before_text.splitlines(keepends=True),
        after_text.splitlines(keepends=True),
        fromfile=f"a/{relative}",
        tofile=f"b/{relative}",
        lineterm="\n",
    )
    payload = f"diff --git a/{relative} b/{relative}\n" + "".join(diff)
    if "@@ " not in payload:
        raise ComponentInterfaceError("deterministic patch contains no textual hunk")
    return payload.encode("utf-8")


def _write_bundle(
    destination: Path,
    relative: str,
    neutral: bytes,
    source_context: bytes,
    functional: bytes,
) -> dict[str, Any]:
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite derived candidate: {destination}")
    if len({neutral, source_context, functional}) != 3:
        raise ComponentInterfaceError("B, U, and R service bytes must be distinct")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="controlled-v3-component-adapter-", dir=destination.parent
    ) as temporary:
        staged = Path(temporary) / "candidate"
        service = staged / "B" / relative
        service.parent.mkdir(parents=True)
        service.write_bytes(neutral)
        service.chmod(0o644)
        feature = canonical_patch(neutral, source_context, relative)
        security = canonical_patch(source_context, functional, relative)
        (staged / "feature.patch").write_bytes(feature)
        (staged / "security.patch").write_bytes(security)
        for patch in (staged / "feature.patch", staged / "security.patch"):
            patch.chmod(0o644)
        shutil.copytree(staged, destination)
    return {
        "schema_version": "controlled-v3-derived-candidate/1",
        "service_path": relative,
        "state_service_sha256": {
            "B": _sha256(neutral),
            "U": _sha256(source_context),
            "R": _sha256(functional),
        },
        "feature_patch_sha256": _sha256(feature),
        "security_patch_sha256": _sha256(security),
        "constructor_authored_states": ["B", "R"],
        "locally_derived_states": ["U"],
    }


def build_candidate(components: Path, destination: Path, family_id: str) -> dict[str, Any]:
    authored = read_components(components, family_id)
    report = _write_bundle(
        destination,
        service_path(family_id),
        authored["neutral_target"],
        frozen_source_context(family_id),
        authored["functional_target"],
    )
    report["family_id"] = family_id
    report["component_sha256"] = {
        name: _sha256(value) for name, value in authored.items()
    }
    return report


def build_dummy_candidate(
    components: Path, destination: Path, source_context: Path
) -> dict[str, Any]:
    relative = "app/service.py"
    root = Path(components)
    expected_directories = {
        ".",
        "neutral_target",
        "neutral_target/app",
        "functional_target",
        "functional_target/app",
    }
    expected_files = {
        "neutral_target/app/service.py",
        "functional_target/app/service.py",
    }
    if root.is_symlink() or not root.is_dir():
        raise ComponentInterfaceError("dummy components must be a real directory")
    directories: set[str] = set()
    files: set[str] = set()
    for path in (root, *root.rglob("*")):
        name = path.relative_to(root).as_posix() or "."
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode) and not path.is_symlink():
            directories.add(name)
        elif stat.S_ISREG(metadata.st_mode) and not path.is_symlink():
            files.add(name)
        else:
            raise ComponentInterfaceError(f"special or linked dummy path: {name}")
    if directories != expected_directories or files != expected_files:
        raise ComponentInterfaceError(
            "dummy component tree differs: "
            f"dirs={sorted(directories)} files={sorted(files)}"
        )
    neutral = _read_component(root / "neutral_target" / relative)
    functional = _read_component(root / "functional_target" / relative)
    source = _read_component(Path(source_context))
    return _write_bundle(destination, relative, neutral, source, functional)


def round_trip_states(candidate: Path, relative: str) -> dict[str, bytes]:
    """Materialize a derived bundle without executing it (dummy/interface use)."""
    candidate = Path(candidate)
    expected = {"B", "feature.patch", "security.patch"}
    if {path.name for path in candidate.iterdir()} != expected:
        raise ComponentInterfaceError("derived candidate top-level shape differs")
    with tempfile.TemporaryDirectory(prefix="controlled-v3-round-trip-") as temporary:
        root = Path(temporary)
        for state in ("B", "U", "R"):
            shutil.copytree(candidate / "B", root / state)
        environment = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
        commands = (
            (root / "U", candidate / "feature.patch"),
            (root / "R", candidate / "feature.patch"),
            (root / "R", candidate / "security.patch"),
        )
        for tree, patch in commands:
            completed = subprocess.run(
                [
                    "git",
                    "-c",
                    "core.safecrlf=true",
                    "apply",
                    "--no-index",
                    "--whitespace=error-all",
                    str(patch.resolve()),
                ],
                cwd=tree,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=10,
                env=environment,
            )
            if completed.returncode:
                raise ComponentInterfaceError(
                    "derived patch failed round-trip: "
                    + completed.stderr.decode("utf-8", "replace")[:300]
                )
        return {state: (root / state / relative).read_bytes() for state in ("B", "U", "R")}


def snapshot(root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    root = Path(root)
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode) and not path.is_symlink():
            rows.append({"path": relative, "type": "directory"})
        elif stat.S_ISREG(metadata.st_mode) and not path.is_symlink():
            value = path.read_bytes()
            rows.append(
                {
                    "path": relative,
                    "type": "file",
                    "bytes": len(value),
                    "sha256": _sha256(value),
                }
            )
        elif path.is_symlink():
            rows.append({"path": relative, "type": "symlink", "target": os.readlink(path)})
        else:
            rows.append({"path": relative, "type": "special"})
    return {"entries": rows, "tree_sha256": _sha256(_canonical(rows))}
