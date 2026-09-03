"""Authoritative append-only content access mediation for confirmatory V4."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sqlite3
from typing import Any, Mapping, Sequence
import uuid


class ContentAuditV4Error(RuntimeError):
    """A critical content read escaped its frozen boundary or audit chain."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


@dataclass(frozen=True)
class ArtifactRef:
    """An immutable file named relative to one prospectively allowed boundary."""

    logical_resource: str
    boundary: str
    relative_path: str
    sha256: str

    def __post_init__(self) -> None:
        relative = PurePosixPath(self.relative_path)
        if (
            not self.logical_resource
            or not self.boundary
            or relative.is_absolute()
            or not relative.parts
            or ".." in relative.parts
        ):
            raise ContentAuditV4Error("invalid immutable artifact reference")
        if len(self.sha256) != 64 or any(c not in "0123456789abcdef" for c in self.sha256):
            raise ContentAuditV4Error("artifact reference has an invalid SHA-256")


@dataclass(frozen=True)
class TreeRef:
    """An immutable non-Git tree named relative to an allowed boundary."""

    logical_resource: str
    boundary: str
    relative_path: str
    sha256: str

    def __post_init__(self) -> None:
        ArtifactRef(
            logical_resource=self.logical_resource,
            boundary=self.boundary,
            relative_path=self.relative_path,
            sha256=self.sha256,
        )


class ContentAccessAudit:
    """Global, durable audit authority used by every V4 production content read.

    SQLite serializes writers across processes. Database triggers prohibit update
    and delete, while a SHA-256 chain makes record loss or reordering detectable.
    There is intentionally no in-memory read counter that can stand in for this
    ledger.
    """

    def __init__(
        self,
        database: Path,
        *,
        boundaries: Mapping[str, Path],
        phase: str,
        session_id: str | None = None,
    ) -> None:
        if not phase:
            raise ContentAuditV4Error("audit phase is required")
        self.database = Path(database).resolve()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.phase = phase
        self.session_id = session_id or str(uuid.uuid4())
        self.process_id = os.getpid()
        self._boundaries: dict[str, Path] = {}
        for name, root in boundaries.items():
            resolved = Path(root).resolve(strict=True)
            if not name or not resolved.is_dir() or resolved.is_symlink():
                raise ContentAuditV4Error("audit boundaries must be real directories")
            self._boundaries[name] = resolved
        if not self._boundaries:
            raise ContentAuditV4Error("at least one audit boundary is required")
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=60, isolation_level=None)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS content_access (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_utc TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    process_id INTEGER NOT NULL,
                    session_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    source_id TEXT,
                    logical_resource TEXT NOT NULL,
                    content_identifier TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    allowed_boundary TEXT NOT NULL,
                    caller TEXT NOT NULL,
                    byte_count INTEGER NOT NULL,
                    previous_event_sha256 TEXT NOT NULL,
                    event_sha256 TEXT NOT NULL UNIQUE
                );
                CREATE TRIGGER IF NOT EXISTS content_access_no_update
                BEFORE UPDATE ON content_access
                BEGIN SELECT RAISE(ABORT, 'content audit is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS content_access_no_delete
                BEFORE DELETE ON content_access
                BEGIN SELECT RAISE(ABORT, 'content audit is append-only'); END;
                """
            )

    def _path(self, boundary: str, relative_path: str, *, directory: bool) -> Path:
        if boundary not in self._boundaries:
            raise ContentAuditV4Error("artifact names an unregistered boundary")
        relative = PurePosixPath(relative_path)
        if relative.is_absolute() or not relative.parts or ".." in relative.parts:
            raise ContentAuditV4Error("artifact path escapes its allowed boundary")
        root = self._boundaries[boundary]
        candidate = root.joinpath(*relative.parts)
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (FileNotFoundError, OSError, ValueError) as error:
            raise ContentAuditV4Error("critical artifact is missing or escaped") from error
        current = root
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ContentAuditV4Error("critical artifact path contains a symlink")
        valid = resolved.is_dir() if directory else resolved.is_file()
        if not valid:
            raise ContentAuditV4Error("critical artifact has the wrong filesystem type")
        return resolved

    def _append(
        self,
        *,
        target_id: str,
        source_id: str | None,
        logical_resource: str,
        content_identifier: str,
        digest: str,
        boundary: str,
        caller: str,
        byte_count: int,
    ) -> str:
        values = self._append_batch(
            [
                {
                    "target_id": target_id,
                    "source_id": source_id,
                    "logical_resource": logical_resource,
                    "content_identifier": content_identifier,
                    "digest": digest,
                    "boundary": boundary,
                    "caller": caller,
                    "byte_count": byte_count,
                }
            ]
        )
        return values[0]

    def _append_batch(self, records: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
        if not records:
            return ()
        for record in records:
            if not record["target_id"] or not record["caller"] or not record["logical_resource"]:
                raise ContentAuditV4Error("audit identity fields are required")
        hashes: list[str] = []
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            previous_row = connection.execute(
                "SELECT event_sha256 FROM content_access ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            previous = "0" * 64 if previous_row is None else str(previous_row[0])
            for record in records:
                timestamp = datetime.now(timezone.utc).isoformat()
                body = {
                    "timestamp_utc": timestamp,
                    "phase": self.phase,
                    "process_id": self.process_id,
                    "session_id": self.session_id,
                    "target_id": record["target_id"],
                    "source_id": record["source_id"],
                    "logical_resource": record["logical_resource"],
                    "content_identifier": record["content_identifier"],
                    "sha256": record["digest"],
                    "allowed_boundary": record["boundary"],
                    "caller": record["caller"],
                    "byte_count": record["byte_count"],
                    "previous_event_sha256": previous,
                }
                event_hash = sha256_bytes(_canonical(body))
                connection.execute(
                    """
                    INSERT INTO content_access (
                        timestamp_utc, phase, process_id, session_id, target_id,
                        source_id, logical_resource, content_identifier, sha256,
                        allowed_boundary, caller, byte_count, previous_event_sha256,
                        event_sha256
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                    timestamp,
                    self.phase,
                    self.process_id,
                    self.session_id,
                    record["target_id"],
                    record["source_id"],
                    record["logical_resource"],
                    record["content_identifier"],
                    record["digest"],
                    record["boundary"],
                    record["caller"],
                    record["byte_count"],
                    previous,
                    event_hash,
                    ),
                )
                hashes.append(event_hash)
                previous = event_hash
            connection.execute("COMMIT")
        return tuple(hashes)

    def read_bytes(
        self,
        artifact: ArtifactRef,
        *,
        target_id: str,
        source_id: str | None,
        caller: str,
    ) -> bytes:
        if not isinstance(artifact, ArtifactRef):
            raise ContentAuditV4Error("critical file reads require an ArtifactRef")
        path = self._path(artifact.boundary, artifact.relative_path, directory=False)
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb", closefd=True) as handle:
            data = handle.read()
        digest = sha256_bytes(data)
        if digest != artifact.sha256:
            raise ContentAuditV4Error("critical artifact SHA-256 mismatch")
        self._append(
            target_id=target_id,
            source_id=source_id,
            logical_resource=artifact.logical_resource,
            content_identifier=artifact.relative_path,
            digest=digest,
            boundary=artifact.boundary,
            caller=caller,
            byte_count=len(data),
        )
        return data

    def bind_development_file(
        self,
        *,
        logical_resource: str,
        boundary: str,
        relative_path: str,
        target_id: str,
        source_id: str | None,
        caller: str,
    ) -> ArtifactRef:
        """Hash and log an already excluded development file before registry use.

        Confirmatory production must use prospectively frozen ``ArtifactRef``
        values. This method exists only to build the final development registry
        without an unaudited bootstrap read.
        """

        if not self.phase.startswith("V4_DEVELOPMENT"):
            raise ContentAuditV4Error("development binding is unavailable in confirmation")
        path = self._path(boundary, relative_path, directory=False)
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(descriptor, "rb", closefd=True) as handle:
            data = handle.read()
        digest = sha256_bytes(data)
        self._append(
            target_id=target_id,
            source_id=source_id,
            logical_resource=f"BINDING:{logical_resource}",
            content_identifier=relative_path,
            digest=digest,
            boundary=boundary,
            caller=caller,
            byte_count=len(data),
        )
        return ArtifactRef(logical_resource, boundary, relative_path, digest)

    def verify_tree(
        self,
        tree: TreeRef,
        *,
        target_id: str,
        source_id: str | None,
        caller: str,
        exclude: Sequence[str] = (".git",),
    ) -> Path:
        if not isinstance(tree, TreeRef):
            raise ContentAuditV4Error("critical tree reads require a TreeRef")
        root = self._path(tree.boundary, tree.relative_path, directory=True)
        excluded = set(exclude)
        digest = hashlib.sha256()
        byte_count = 0
        file_events: list[dict[str, Any]] = []
        paths = sorted(path for path in root.rglob("*") if path.is_file() or path.is_symlink())
        for path in paths:
            relative = path.relative_to(root)
            if any(part in excluded for part in relative.parts):
                continue
            if path.is_symlink():
                data = path.readlink().as_posix().encode("utf-8")
                kind = b"symlink\0"
            else:
                data = path.read_bytes()
                kind = b"file\0"
            file_digest = sha256_bytes(data)
            byte_count += len(data)
            encoded = relative.as_posix().encode("utf-8")
            digest.update(encoded)
            digest.update(b"\0")
            digest.update(kind)
            digest.update(data)
            digest.update(b"\0")
            file_events.append(
                {
                    "target_id": target_id,
                    "source_id": source_id,
                    "logical_resource": f"{tree.logical_resource}:FILE",
                    "content_identifier": f"{tree.relative_path}/{relative.as_posix()}",
                    "digest": file_digest,
                    "boundary": tree.boundary,
                    "caller": caller,
                    "byte_count": len(data),
                }
            )
        observed = digest.hexdigest()
        self._append_batch(file_events)
        if observed != tree.sha256:
            raise ContentAuditV4Error("critical tree SHA-256 mismatch")
        self._append(
            target_id=target_id,
            source_id=source_id,
            logical_resource=tree.logical_resource,
            content_identifier=tree.relative_path,
            digest=observed,
            boundary=tree.boundary,
            caller=caller,
            byte_count=byte_count,
        )
        return root

    def events(self) -> tuple[dict[str, Any], ...]:
        with self._connect() as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT * FROM content_access ORDER BY sequence"
            ).fetchall()
        return tuple(dict(row) for row in rows)

    def verify_chain(self) -> str:
        previous = "0" * 64
        events = self.events()
        for expected_sequence, event in enumerate(events, 1):
            if event["sequence"] != expected_sequence:
                raise ContentAuditV4Error("content audit sequence has a gap")
            body = {
                key: event[key]
                for key in (
                    "timestamp_utc",
                    "phase",
                    "process_id",
                    "session_id",
                    "target_id",
                    "source_id",
                    "logical_resource",
                    "content_identifier",
                    "sha256",
                    "allowed_boundary",
                    "caller",
                    "byte_count",
                    "previous_event_sha256",
                )
            }
            if body["previous_event_sha256"] != previous:
                raise ContentAuditV4Error("content audit predecessor mismatch")
            observed = sha256_bytes(_canonical(body))
            if observed != event["event_sha256"]:
                raise ContentAuditV4Error("content audit event hash mismatch")
            previous = observed
        return previous
