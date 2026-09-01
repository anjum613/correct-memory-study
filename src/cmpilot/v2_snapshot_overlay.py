"""Reconstruct V2 snapshots from Git-visible trees and frozen byte overlays."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile
from typing import Any

from .repository_manager import repository_content_digest


OVERLAY_SCHEMA = "cmpilot-v2-snapshot-overlays-v1"


class SnapshotOverlayError(RuntimeError):
    """A frozen overlay or reconstructed snapshot failed closed."""


@dataclass(frozen=True)
class ReconstructedSnapshot:
    family: str
    state: str
    destination: Path
    repository_sha256: str
    overlay_file_count: int


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_overlay_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != OVERLAY_SCHEMA:
        raise SnapshotOverlayError(f"invalid snapshot-overlay manifest: {path}")
    families = value.get("families")
    if not isinstance(families, dict) or not families:
        raise SnapshotOverlayError("snapshot-overlay manifest has no families")
    return value


def _safe_member_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if not name or path.is_absolute() or ".." in path.parts or "." in path.parts:
        raise SnapshotOverlayError(f"unsafe overlay member path: {name!r}")
    if path.as_posix() != name:
        raise SnapshotOverlayError(f"non-canonical overlay member path: {name!r}")
    return path


def _family_record(manifest: dict[str, Any], family: str) -> dict[str, Any]:
    record = manifest["families"].get(family)
    if not isinstance(record, dict):
        raise SnapshotOverlayError(f"family absent from overlay manifest: {family}")
    return record


def verify_overlay_archive(manifest_path: Path, family: str) -> dict[str, Any]:
    manifest_path = Path(manifest_path)
    manifest = load_overlay_manifest(manifest_path)
    record = _family_record(manifest, family)
    archive = manifest_path.parent / str(record.get("archive"))
    if not archive.is_file():
        raise SnapshotOverlayError(f"overlay archive is absent: {archive}")
    if _sha256(archive) != record.get("archive_sha256"):
        raise SnapshotOverlayError(f"overlay archive hash mismatch: {archive}")

    declared = record.get("files")
    if not isinstance(declared, list) or not declared:
        raise SnapshotOverlayError(f"overlay file inventory is empty: {family}")
    expected = {str(row["archive_path"]): row for row in declared}
    if len(expected) != len(declared):
        raise SnapshotOverlayError(f"duplicate declared overlay path: {family}")

    observed: set[str] = set()
    with tarfile.open(archive, mode="r:gz") as bundle:
        for member in bundle.getmembers():
            _safe_member_path(member.name)
            if not member.isfile():
                raise SnapshotOverlayError(
                    f"overlay contains a non-regular member: {member.name}"
                )
            row = expected.get(member.name)
            if row is None:
                raise SnapshotOverlayError(f"undeclared overlay member: {member.name}")
            if member.name in observed:
                raise SnapshotOverlayError(f"duplicate overlay member: {member.name}")
            stream = bundle.extractfile(member)
            if stream is None:
                raise SnapshotOverlayError(f"overlay member is unreadable: {member.name}")
            payload = stream.read()
            if len(payload) != row.get("bytes"):
                raise SnapshotOverlayError(f"overlay member size mismatch: {member.name}")
            if hashlib.sha256(payload).hexdigest() != row.get("sha256"):
                raise SnapshotOverlayError(f"overlay member hash mismatch: {member.name}")
            observed.add(member.name)
    if observed != set(expected):
        missing = sorted(set(expected) - observed)
        raise SnapshotOverlayError(f"overlay archive is incomplete: {missing}")
    return record


def reconstruct_snapshot(
    *,
    repository_root: Path,
    manifest_path: Path,
    family: str,
    state: str,
    destination: Path,
) -> ReconstructedSnapshot:
    """Reconstruct one exact V2 input without a historical dirty worktree."""
    repository_root = Path(repository_root)
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise SnapshotOverlayError(f"destination already exists: {destination}")

    manifest = load_overlay_manifest(manifest_path)
    record = verify_overlay_archive(manifest_path, family)
    state_record = record.get("states", {}).get(state)
    if not isinstance(state_record, dict):
        raise SnapshotOverlayError(f"unknown overlay state: {family}/{state}")

    source = repository_root / "families" / family / "repositories" / state
    if not source.is_dir():
        raise SnapshotOverlayError(f"Git-visible snapshot is absent: {source}")
    expected_clean = str(state_record.get("git_visible_repository_sha256"))
    observed_clean = repository_content_digest(source).sha256
    if observed_clean != expected_clean:
        raise SnapshotOverlayError(
            f"Git-visible snapshot hash mismatch for {family}/{state}: {observed_clean}"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, symlinks=True)
    relevant = {
        str(row["archive_path"]): row
        for row in record["files"]
        if row.get("state") == state
    }
    archive = Path(manifest_path).parent / str(record["archive"])
    with tarfile.open(archive, mode="r:gz") as bundle:
        for member in bundle.getmembers():
            row = relevant.get(member.name)
            if row is None:
                continue
            relative = PurePosixPath(str(row["relative_path"]))
            _safe_member_path(relative.as_posix())
            target = destination.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() or target.is_symlink():
                raise SnapshotOverlayError(f"overlay would overwrite a Git file: {target}")
            stream = bundle.extractfile(member)
            if stream is None:
                raise SnapshotOverlayError(f"overlay member is unreadable: {member.name}")
            payload = stream.read()
            target.write_bytes(payload)
            target.chmod(int(str(row["mode"]), 8))

    observed = repository_content_digest(destination).sha256
    expected = str(state_record.get("reconstructed_repository_sha256"))
    if observed != expected:
        raise SnapshotOverlayError(
            f"reconstructed snapshot hash mismatch for {family}/{state}: {observed}"
        )
    return ReconstructedSnapshot(
        family=family,
        state=state,
        destination=destination,
        repository_sha256=observed,
        overlay_file_count=len(relevant),
    )
