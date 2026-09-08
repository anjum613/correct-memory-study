"""Canonical SHA-256 handling for project-owned runtime artifacts."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re


SHA256_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class FileDigestError(RuntimeError):
    """A file could not be hashed exactly as stored."""


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 of the exact bytes in *path*."""
    path = Path(path)
    if not path.exists():
        raise FileDigestError(f"digest input does not exist: {path}")
    if not path.is_file():
        raise FileDigestError(f"digest input is not a regular file: {path}")
    try:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise FileDigestError(f"digest input is unreadable: {path}: {error}") from error
    value = digest.hexdigest()
    if not SHA256_HEX_PATTERN.fullmatch(value):  # pragma: no cover - invariant
        raise FileDigestError(f"invalid SHA-256 produced for {path}")
    return value


def validate_sha256_hex(value: str, *, name: str = "digest") -> str:
    """Require a plain lowercase 64-character hexadecimal digest."""
    if not SHA256_HEX_PATTERN.fullmatch(value):
        raise FileDigestError(
            f"{name} must be exactly 64 lowercase hexadecimal characters"
        )
    return value
