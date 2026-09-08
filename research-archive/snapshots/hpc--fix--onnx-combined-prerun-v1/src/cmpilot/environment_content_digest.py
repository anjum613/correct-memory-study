"""Stable, content-authoritative integrity digests for frozen environments."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import importlib.metadata as importlib_metadata
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import unicodedata

from cmpilot.environment_fingerprint import canonicalize_distribution_name


CONTENT_DIGEST_SCHEMA = "environment-content-digest-v1"
METADATA_OBSERVATION_SCHEMA = "environment-metadata-observation-v1"
CONTENT_UNCHANGED_METADATA_DIFFERED = (
    "ENVIRONMENT_CONTENT_UNCHANGED_METADATA_DIFFERED"
)
CONTENT_CHANGED = "ENVIRONMENT_CONTENT_CHANGED"
CONTENT_MATCH = "ENVIRONMENT_CONTENT_MATCH"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_SUPPORTED_TYPES = frozenset({"file", "symlink"})


class ContentDigestError(ValueError):
    """Raised when stable environment-content input cannot be canonicalized."""


@dataclass(frozen=True)
class ContentDigestResult:
    """Canonical content inventory and its SHA-256."""

    canonical_inventory: bytes
    sha256: str
    entry_count: int
    package_count: int
    profile: str
    schema: str = CONTENT_DIGEST_SCHEMA

    def as_record(self) -> dict[str, object]:
        return {
            "authoritative": True,
            "canonical_inventory_sha256": self.sha256,
            "entry_count": self.entry_count,
            "package_count": self.package_count,
            "profile": self.profile,
            "schema": self.schema,
        }


def _normalize_text(value: object, *, field: str) -> str:
    if not isinstance(value, str):
        raise ContentDigestError(f"{field} must be text")
    if "\0" in value:
        raise ContentDigestError(f"{field} must not contain NUL")
    line_normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    return unicodedata.normalize("NFC", line_normalized)


def _normalize_inventory_path(value: object) -> str:
    normalized = _normalize_text(value, field="content path").replace("\\", "/")
    if not normalized or normalized.startswith("/"):
        raise ContentDigestError("content path must be non-empty and relative")
    # PurePosixPath removes redundant separators and '.' without consulting a FS.
    result = str(PurePosixPath(normalized))
    if result in {"", "."}:
        raise ContentDigestError("content path must identify an entry")
    return result


def _safe_source_relative_path(value: str) -> Path:
    normalized = _normalize_inventory_path(value)
    path = PurePosixPath(normalized)
    if ".." in path.parts:
        raise ContentDigestError(f"source path escapes its root: {value!r}")
    return Path(*path.parts)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record_for_path(path: Path, canonical_path: str) -> dict[str, str]:
    information = path.lstat()
    if stat.S_ISLNK(information.st_mode):
        return {
            "path": _normalize_inventory_path(canonical_path),
            "target": _normalize_text(
                os.readlink(path).replace("\\", "/"), field="symlink target"
            ),
            "type": "symlink",
        }
    if stat.S_ISREG(information.st_mode):
        return {
            "path": _normalize_inventory_path(canonical_path),
            "sha256": sha256_file(path),
            "type": "file",
        }
    raise ContentDigestError(f"unsupported required file type: {path}")


def collect_content_records(
    root: Path, relative_paths: Iterable[str]
) -> list[dict[str, str]]:
    """Hash explicitly selected paths without using enumeration order or metadata."""
    root = root.resolve(strict=True)
    records: list[dict[str, str]] = []
    for raw_relative in relative_paths:
        relative = _safe_source_relative_path(raw_relative)
        path = root / relative
        if not path.exists() and not path.is_symlink():
            raise ContentDigestError(f"required content path does not exist: {path}")
        records.append(_record_for_path(path, relative.as_posix()))
    return records


def _canonical_content_record(record: Mapping[str, object]) -> dict[str, str]:
    if not isinstance(record, Mapping):
        raise ContentDigestError("each content record must be an object")
    kind = record.get("type")
    if kind not in _SUPPORTED_TYPES:
        raise ContentDigestError(f"unsupported content record type: {kind!r}")
    expected_fields = {"path", "type", "sha256" if kind == "file" else "target"}
    unexpected = set(record) - expected_fields
    missing = expected_fields - set(record)
    if missing or unexpected:
        raise ContentDigestError(
            f"invalid {kind} record fields; missing={sorted(missing)}, "
            f"unexpected={sorted(unexpected)}"
        )
    result = {
        "path": _normalize_inventory_path(record["path"]),
        "type": str(kind),
    }
    if kind == "file":
        digest = record["sha256"]
        if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
            raise ContentDigestError("file sha256 must be a lowercase SHA-256")
        result["sha256"] = digest
    else:
        result["target"] = _normalize_text(record["target"], field="symlink target")
    return result


def _canonical_package_record(record: Mapping[str, object]) -> dict[str, str]:
    if not isinstance(record, Mapping) or set(record) != {"name", "version"}:
        raise ContentDigestError("package records require exactly name and version")
    return {
        "name": canonicalize_distribution_name(record["name"]),
        "version": _normalize_text(record["version"], field="package version"),
    }


def fingerprint_content(
    entries: Iterable[Mapping[str, object]],
    *,
    packages: Iterable[Mapping[str, object]] = (),
    profile: str,
) -> ContentDigestResult:
    """Create a canonical UTF-8/LF digest from stable content fields only."""
    canonical_entries = [_canonical_content_record(record) for record in entries]
    canonical_entries.sort(
        key=lambda row: (
            row["path"],
            row["type"],
            row.get("sha256", ""),
            row.get("target", ""),
        )
    )
    paths = [row["path"] for row in canonical_entries]
    if len(paths) != len(set(paths)):
        raise ContentDigestError("content inventory contains duplicate paths")
    canonical_packages = [_canonical_package_record(record) for record in packages]
    canonical_packages.sort(key=lambda row: (row["name"], row["version"]))
    names = [row["name"] for row in canonical_packages]
    if len(names) != len(set(names)):
        raise ContentDigestError("content inventory contains duplicate package names")
    normalized_profile = _normalize_text(profile, field="content profile")
    if not normalized_profile:
        raise ContentDigestError("content profile must not be empty")
    payload = {
        "entries": canonical_entries,
        "packages": canonical_packages,
        "profile": normalized_profile,
        "schema": CONTENT_DIGEST_SCHEMA,
    }
    canonical = (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    return ContentDigestResult(
        canonical_inventory=canonical,
        sha256=hashlib.sha256(canonical).hexdigest(),
        entry_count=len(canonical_entries),
        package_count=len(canonical_packages),
        profile=normalized_profile,
    )


def observe_metadata(root: Path, relative_paths: Iterable[str]) -> dict[str, object]:
    """Record unstable filesystem metadata as explicitly non-authoritative data."""
    root = root.resolve(strict=True)
    entries: list[dict[str, object]] = []
    for raw_relative in sorted(relative_paths, key=str):
        relative = _safe_source_relative_path(raw_relative)
        information = (root / relative).lstat()
        entries.append(
            {
                "ctime_ns": information.st_ctime_ns,
                "device": information.st_dev,
                "gid": information.st_gid,
                "inode": information.st_ino,
                "mode": stat.S_IMODE(information.st_mode),
                "mtime_ns": information.st_mtime_ns,
                "path": relative.as_posix(),
                "uid": information.st_uid,
            }
        )
    return {
        "authoritative": False,
        "entries": entries,
        "schema": METADATA_OBSERVATION_SCHEMA,
    }


def _load_json_object(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ContentDigestError(f"cannot read content inventory {path}: {error}") from error
    if not isinstance(value, dict):
        raise ContentDigestError(f"content inventory must be an object: {path}")
    return value


def fingerprint_recorded_distribution_snapshot(
    files_path: Path,
    summary_path: Path,
    *,
    read_current_bytes: bool,
) -> ContentDigestResult:
    """Digest the preserved 579-file inventory or the same paths on disk now."""
    files_document = _load_json_object(files_path)
    summary_document = _load_json_object(summary_path)
    entries: list[dict[str, str]] = []
    packages: list[dict[str, str]] = []
    for inventory_name in sorted(files_document):
        package_value = files_document[inventory_name]
        summary_value = summary_document.get(inventory_name)
        if not isinstance(package_value, dict) or not isinstance(summary_value, dict):
            raise ContentDigestError(f"invalid distribution inventory: {inventory_name}")
        file_values = package_value.get("files")
        if not isinstance(file_values, list):
            raise ContentDigestError(f"distribution files must be a list: {inventory_name}")
        package_name = canonicalize_distribution_name(
            str(summary_value.get("metadata_name", inventory_name))
        )
        version = summary_value.get("version")
        if not isinstance(version, str):
            raise ContentDigestError(f"distribution version is missing: {inventory_name}")
        packages.append({"name": package_name, "version": version})
        for value in file_values:
            if not isinstance(value, dict):
                raise ContentDigestError("recorded distribution file must be an object")
            record_path = _normalize_inventory_path(value.get("record_path"))
            canonical_path = f"distributions/{package_name}/{record_path}"
            if read_current_bytes:
                installed_path = value.get("installed_path")
                if not isinstance(installed_path, str) or not installed_path.startswith("/"):
                    raise ContentDigestError("installed_path must be absolute")
                path = Path(installed_path)
                if not path.exists() and not path.is_symlink():
                    raise ContentDigestError(f"recorded package file is missing: {path}")
                entries.append(_record_for_path(path, canonical_path))
            else:
                digest = value.get("sha256")
                if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
                    raise ContentDigestError("recorded package sha256 is invalid")
                entries.append(
                    {"path": canonical_path, "sha256": digest, "type": "file"}
                )
    return fingerprint_content(
        entries,
        packages=packages,
        profile="guided-backend-four-distribution-files",
    )


def fingerprint_installed_distributions(
    distribution_names: Sequence[str],
    *,
    environment_root: Path | None = None,
    include_interpreter: bool = True,
) -> ContentDigestResult:
    """Hash current distribution files, exact versions, and interpreter content."""
    root = (environment_root or Path(sys.prefix)).resolve(strict=True)
    entries: list[dict[str, str]] = []
    packages: list[dict[str, str]] = []
    for requested_name in distribution_names:
        distribution = importlib_metadata.distribution(requested_name)
        metadata_name = distribution.metadata.get("Name")
        if metadata_name is None:
            raise ContentDigestError(f"distribution has no Name: {requested_name}")
        package_name = canonicalize_distribution_name(metadata_name)
        packages.append({"name": package_name, "version": distribution.version})
        files = distribution.files
        if files is None:
            raise ContentDigestError(f"distribution has no file inventory: {package_name}")
        for distribution_file in files:
            path = Path(os.path.abspath(distribution.locate_file(distribution_file)))
            try:
                environment_relative = path.relative_to(root)
            except ValueError as error:
                raise ContentDigestError(
                    f"distribution file is outside environment root: {path}"
                ) from error
            canonical_path = (
                f"distributions/{package_name}/{environment_relative.as_posix()}"
            )
            entries.append(_record_for_path(path, canonical_path))
    if include_interpreter:
        executable = Path(sys.executable).absolute()
        try:
            executable_relative = executable.relative_to(root)
        except ValueError as error:
            raise ContentDigestError(
                f"interpreter is outside environment root: {executable}"
            ) from error
        entries.append(
            _record_for_path(
                executable, f"interpreter/{executable_relative.as_posix()}"
            )
        )
        if executable.is_symlink():
            resolved = executable.resolve(strict=True)
            entries.append(
                _record_for_path(
                    resolved, f"interpreter-resolved/{resolved.name}"
                )
            )
    return fingerprint_content(
        entries,
        packages=packages,
        profile="guided-backend-runtime-environment",
    )


def write_content_digest_artifacts(
    inventory_path: Path, record_path: Path, result: ContentDigestResult
) -> None:
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.parent.mkdir(parents=True, exist_ok=True)
    inventory_path.write_bytes(result.canonical_inventory)
    record_path.write_text(
        json.dumps(result.as_record(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def classify_content_comparison(
    expected: Mapping[str, object],
    actual: Mapping[str, object],
    *,
    metadata_differed: bool,
) -> dict[str, object]:
    """Compare authoritative content while keeping metadata observational."""
    for name, record in (("expected", expected), ("actual", actual)):
        if record.get("schema") != CONTENT_DIGEST_SCHEMA:
            raise ContentDigestError(
                f"{name} content record is not {CONTENT_DIGEST_SCHEMA}"
            )
        digest = record.get("canonical_inventory_sha256")
        if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
            raise ContentDigestError(f"{name} content digest is invalid")
    content_matches = (
        expected["canonical_inventory_sha256"]
        == actual["canonical_inventory_sha256"]
        and expected.get("profile") == actual.get("profile")
        and expected.get("entry_count") == actual.get("entry_count")
        and expected.get("package_count") == actual.get("package_count")
    )
    if not content_matches:
        label = CONTENT_CHANGED
    elif metadata_differed:
        label = CONTENT_UNCHANGED_METADATA_DIFFERED
    else:
        label = CONTENT_MATCH
    return {
        "actual_content_sha256": actual["canonical_inventory_sha256"],
        "authoritative_content_matches": content_matches,
        "expected_content_sha256": expected["canonical_inventory_sha256"],
        "label": label,
        "metadata_differed": metadata_differed,
        "metadata_is_authoritative": False,
        "schema": CONTENT_DIGEST_SCHEMA,
    }
