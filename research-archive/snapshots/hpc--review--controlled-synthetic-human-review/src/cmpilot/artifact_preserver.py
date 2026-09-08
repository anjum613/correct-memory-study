"""Atomic, idempotent preservation of an immutable run directory."""

from __future__ import annotations

import errno
import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PreservationResult:
    status: str
    source: str
    destination: str
    file_count: int
    tree_sha256: str


def directory_tree_sha256(root: Path) -> tuple[int, str]:
    """Hash relative paths, modes, and file bytes without following symlinks."""
    digest = hashlib.sha256()
    count = 0
    for path in sorted(root.rglob("*"), key=lambda item: str(item.relative_to(root))):
        relative = str(path.relative_to(root))
        if path.is_symlink():
            kind = b"symlink"
            value = os.readlink(path).encode("utf-8")
        elif path.is_file():
            kind = b"file"
            value = path.read_bytes()
            count += 1
        elif path.is_dir():
            kind = b"directory"
            value = b""
        else:
            continue
        digest.update(kind)
        digest.update(b"\0")
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(oct(path.lstat().st_mode & 0o777).encode("ascii"))
        digest.update(b"\0")
        digest.update(value)
        digest.update(b"\0")
    return count, digest.hexdigest()


def atomic_preserve_directory(source: Path, destination: Path) -> PreservationResult:
    """Copy once to a sibling temporary directory, then atomically rename."""
    source = source.resolve()
    destination = destination.absolute()
    if not source.is_dir():
        raise FileNotFoundError(f"preservation source is not a directory: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        count, tree_hash = directory_tree_sha256(destination)
        return PreservationResult(
            "already_preserved", str(source), str(destination), count, tree_hash
        )

    staging_root = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}.preserve-", dir=destination.parent)
    )
    staged = staging_root / "payload"
    try:
        shutil.copytree(source, staged, symlinks=True, copy_function=shutil.copy2)
        expected_count, expected_hash = directory_tree_sha256(staged)
        try:
            os.rename(staged, destination)
            status = "preserved"
        except OSError as error:
            if (
                error.errno not in {errno.EEXIST, errno.ENOTEMPTY}
                or not destination.exists()
            ):
                raise
            status = "already_preserved"
        actual_count, actual_hash = directory_tree_sha256(destination)
        if status == "preserved" and (
            actual_count != expected_count or actual_hash != expected_hash
        ):
            raise RuntimeError("atomic preservation changed the copied tree")
        return PreservationResult(
            status, str(source), str(destination), actual_count, actual_hash
        )
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)
