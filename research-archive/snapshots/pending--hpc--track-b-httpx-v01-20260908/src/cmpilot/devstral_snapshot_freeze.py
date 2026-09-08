"""Content-authoritative freeze support for the pinned Devstral snapshot."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Mapping

from .devstral_profile import (
    AGENT_ENVIRONMENT_ID,
    CANDIDATE_AGENT_FREEZE,
    CANDIDATE_AGENT_FREEZE_SHA256,
    CANDIDATE_AGENT_LOCK,
    CANDIDATE_AGENT_LOCK_SHA256,
    CANDIDATE_FREEZE,
    CANDIDATE_FREEZE_SHA256,
    CANDIDATE_LOCK,
    CANDIDATE_LOCK_SHA256,
    CONFIG_FORMAT,
    ENVIRONMENT_CONTENT_DIGEST_SHA256,
    ENVIRONMENT_FINGERPRINT_SHA256,
    ENVIRONMENT_ID,
    EXPECTED_CONSOLIDATED_SHA256,
    EXPECTED_CONSOLIDATED_SIZE,
    GENERATION_SETTINGS,
    LOAD_FORMAT,
    MODEL_ID,
    MODEL_REVISION,
    PROFILE_ID,
    SERVER_SETTINGS,
    SERVED_MODEL_NAME,
    STAGED_SNAPSHOT_FILE_SHA256,
    TOKENIZER_MODE,
)


FREEZE_SCHEMA = "devstral-snapshot-freeze-v1"
SNAPSHOT_FREEZE = Path("qualification/devstral-small-2507-snapshot-freeze.json")
RUNTIME_WEIGHT_FILE = "consolidated.safetensors"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_REVISION = re.compile(r"[0-9a-f]{40}")


class DevstralSnapshotFreezeError(RuntimeError):
    """The staged snapshot or immutable freeze record is invalid."""


@dataclass(frozen=True)
class DevstralSnapshotExpectation:
    """Exact content expected for one Devstral snapshot revision."""

    model_id: str
    revision: str
    metadata_sha256: tuple[tuple[str, str], ...]
    runtime_weight_size: int
    runtime_weight_sha256: str

    def __post_init__(self) -> None:
        if not self.model_id.strip():
            raise ValueError("model_id must not be empty")
        if _REVISION.fullmatch(self.revision) is None:
            raise ValueError("revision must be a lowercase 40-character commit ID")
        if tuple(sorted(self.metadata_sha256)) != self.metadata_sha256:
            raise ValueError("metadata_sha256 must be sorted")
        names = []
        for name, digest in self.metadata_sha256:
            if not name or Path(name).name != name:
                raise ValueError(f"unsafe snapshot file name: {name!r}")
            if name == RUNTIME_WEIGHT_FILE:
                raise ValueError("runtime weight must not be metadata")
            if _SHA256.fullmatch(digest) is None:
                raise ValueError(f"invalid SHA-256 for {name}")
            names.append(name)
        if len(set(names)) != len(names):
            raise ValueError("metadata file names must be unique")
        if self.runtime_weight_size < 1:
            raise ValueError("runtime_weight_size must be positive")
        if _SHA256.fullmatch(self.runtime_weight_sha256) is None:
            raise ValueError("invalid runtime weight SHA-256")

    @property
    def required_files(self) -> tuple[str, ...]:
        return tuple(sorted((*dict(self.metadata_sha256), RUNTIME_WEIGHT_FILE)))


PINNED_DEVSTRAL_SNAPSHOT = DevstralSnapshotExpectation(
    model_id=MODEL_ID,
    revision=MODEL_REVISION,
    metadata_sha256=STAGED_SNAPSHOT_FILE_SHA256,
    runtime_weight_size=EXPECTED_CONSOLIDATED_SIZE,
    runtime_weight_sha256=EXPECTED_CONSOLIDATED_SHA256,
)


@dataclass(frozen=True)
class DevstralSnapshotFreezeValidation:
    """Fail-closed validation result suitable for readiness reporting."""

    valid: bool
    reason: str
    freeze_sha256: str | None = None
    snapshot_identity_sha256: str | None = None

    @property
    def status(self) -> str:
        return "READY" if self.valid else "NOT_READY"

    def as_record(self) -> dict[str, object]:
        return {
            "freeze_sha256": self.freeze_sha256,
            "reason": self.reason,
            "snapshot_identity_sha256": self.snapshot_identity_sha256,
            "status": self.status,
            "valid": self.valid,
        }


def canonical_json_bytes(value: object) -> bytes:
    """Serialize a freeze record deterministically."""
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _identity_sha256(value: object) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def observe_devstral_snapshot(
    snapshot: Path,
    *,
    expectation: DevstralSnapshotExpectation = PINNED_DEVSTRAL_SNAPSHOT,
) -> dict[str, dict[str, object]]:
    """Hash every required file, following a weight symlink by content."""
    snapshot = Path(snapshot)
    if not snapshot.is_dir():
        raise DevstralSnapshotFreezeError(
            f"snapshot directory is missing: {snapshot}"
        )
    if snapshot.name != expectation.revision:
        raise DevstralSnapshotFreezeError(
            "snapshot directory name does not match the pinned revision"
        )

    observed: dict[str, dict[str, object]] = {}
    expected_hashes = {
        **dict(expectation.metadata_sha256),
        RUNTIME_WEIGHT_FILE: expectation.runtime_weight_sha256,
    }
    for name in expectation.required_files:
        entry = snapshot / name
        if not entry.is_file():
            raise DevstralSnapshotFreezeError(f"required snapshot file is missing: {name}")
        resolved = entry.resolve(strict=True)
        if not resolved.is_file():
            raise DevstralSnapshotFreezeError(
                f"snapshot entry does not resolve to a regular file: {name}"
            )
        size = resolved.stat().st_size
        digest = sha256_file(resolved)
        if digest != expected_hashes[name]:
            raise DevstralSnapshotFreezeError(
                f"snapshot SHA-256 mismatch: {name}"
            )
        if name == RUNTIME_WEIGHT_FILE and size != expectation.runtime_weight_size:
            raise DevstralSnapshotFreezeError("runtime weight size mismatch")
        observed[name] = {"sha256": digest, "size": size}
    return observed


def _validate_observation(
    files: Mapping[str, Mapping[str, object]],
    *,
    expectation: DevstralSnapshotExpectation,
) -> dict[str, dict[str, object]]:
    if set(files) != set(expectation.required_files):
        raise DevstralSnapshotFreezeError(
            "observed snapshot files do not exactly cover the required inventory"
        )
    expected_hashes = {
        **dict(expectation.metadata_sha256),
        RUNTIME_WEIGHT_FILE: expectation.runtime_weight_sha256,
    }
    normalized: dict[str, dict[str, object]] = {}
    for name in expectation.required_files:
        row = files[name]
        size = row.get("size")
        digest = row.get("sha256")
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise DevstralSnapshotFreezeError(f"invalid observed size: {name}")
        if digest != expected_hashes[name]:
            raise DevstralSnapshotFreezeError(
                f"snapshot SHA-256 mismatch: {name}"
            )
        if name == RUNTIME_WEIGHT_FILE and size != expectation.runtime_weight_size:
            raise DevstralSnapshotFreezeError("runtime weight size mismatch")
        normalized[name] = {"sha256": digest, "size": size}
    return normalized


def build_devstral_snapshot_freeze(
    files: Mapping[str, Mapping[str, object]],
    *,
    expectation: DevstralSnapshotExpectation = PINNED_DEVSTRAL_SNAPSHOT,
) -> dict[str, object]:
    """Build the deterministic record from an already observed snapshot."""
    files_record = _validate_observation(files, expectation=expectation)
    loader = {
        "config_format": CONFIG_FORMAT,
        "load_format": LOAD_FORMAT,
        "runtime_weight_file": RUNTIME_WEIGHT_FILE,
        "tokenizer_mode": TOKENIZER_MODE,
    }
    tokenizer = {
        "file": "tekken.json",
        "repository_id": expectation.model_id,
        "revision": expectation.revision,
        "sha256": files_record["tekken.json"]["sha256"],
    }
    snapshot_identity = {
        "files": files_record,
        "loader": loader,
        "model_id": expectation.model_id,
        "revision": expectation.revision,
        "tokenizer": tokenizer,
    }
    serving_profile_identity = {
        "generation": GENERATION_SETTINGS.as_record(),
        "model_id": expectation.model_id,
        "model_revision": expectation.revision,
        "profile_id": PROFILE_ID,
        "serialization": {
            "config_format": CONFIG_FORMAT,
            "load_format": LOAD_FORMAT,
            "tokenizer_mode": TOKENIZER_MODE,
        },
        "served_model_name": SERVED_MODEL_NAME,
        "server": {
            "dtype": SERVER_SETTINGS.dtype,
            "gpu_memory_utilization": SERVER_SETTINGS.gpu_memory_utilization,
            "max_model_length": SERVER_SETTINGS.max_model_length,
            "max_num_sequences": SERVER_SETTINGS.max_num_sequences,
            "quantization": SERVER_SETTINGS.quantization,
            "seed": SERVER_SETTINGS.server_seed,
            "tensor_parallel_size": SERVER_SETTINGS.tensor_parallel_size,
        },
    }
    environment_identity = {
        "agent": {
            "environment_id": AGENT_ENVIRONMENT_ID,
            "freeze": str(CANDIDATE_AGENT_FREEZE),
            "freeze_sha256": CANDIDATE_AGENT_FREEZE_SHA256,
            "lock": str(CANDIDATE_AGENT_LOCK),
            "lock_sha256": CANDIDATE_AGENT_LOCK_SHA256,
        },
        "server": {
            "content_digest_sha256": ENVIRONMENT_CONTENT_DIGEST_SHA256,
            "environment_id": ENVIRONMENT_ID,
            "fingerprint_sha256": ENVIRONMENT_FINGERPRINT_SHA256,
            "freeze": str(CANDIDATE_FREEZE),
            "freeze_sha256": CANDIDATE_FREEZE_SHA256,
            "lock": str(CANDIDATE_LOCK),
            "lock_sha256": CANDIDATE_LOCK_SHA256,
        },
    }
    authoritative = {
        "environment": {
            **environment_identity,
            "identity_sha256": _identity_sha256(environment_identity),
        },
        "model": {
            "id": expectation.model_id,
            "revision": expectation.revision,
        },
        "serving_profile": {
            **serving_profile_identity,
            "identity_sha256": _identity_sha256(serving_profile_identity),
        },
        "snapshot": {
            **snapshot_identity,
            "identity_sha256": _identity_sha256(snapshot_identity),
        },
    }
    return {
        **authoritative,
        "freeze_identity_sha256": _identity_sha256(authoritative),
        "schema": FREEZE_SCHEMA,
    }


def create_devstral_snapshot_freeze(
    snapshot: Path,
    *,
    expectation: DevstralSnapshotExpectation = PINNED_DEVSTRAL_SNAPSHOT,
) -> dict[str, object]:
    """Inspect a live snapshot and return its exact deterministic freeze."""
    return build_devstral_snapshot_freeze(
        observe_devstral_snapshot(snapshot, expectation=expectation),
        expectation=expectation,
    )


def write_devstral_snapshot_freeze_atomic(
    path: Path, record: Mapping[str, object]
) -> str:
    """Publish one canonical record atomically without replacing any entry."""
    path = Path(path)
    parent = path.parent.resolve(strict=True)
    destination = parent / path.name
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"freeze output already exists: {destination}")
    payload = canonical_json_bytes(record)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
        directory_descriptor = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary.unlink(missing_ok=True)
    return sha256_bytes(payload)


def _load_canonical_record(path: Path) -> tuple[dict[str, object], bytes]:
    payload = path.read_bytes()
    try:
        record = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DevstralSnapshotFreezeError("freeze record is not valid JSON") from error
    if not isinstance(record, dict):
        raise DevstralSnapshotFreezeError("freeze record must be a JSON object")
    if canonical_json_bytes(record) != payload:
        raise DevstralSnapshotFreezeError("freeze record is not canonical JSON")
    return record, payload


def validate_devstral_snapshot_freeze_observation(
    freeze_path: Path,
    files: Mapping[str, Mapping[str, object]],
    *,
    snapshot_revision: str,
    expectation: DevstralSnapshotExpectation = PINNED_DEVSTRAL_SNAPSHOT,
) -> DevstralSnapshotFreezeValidation:
    """Compare a live observation with the immutable checked-in record."""
    freeze_path = Path(freeze_path)
    try:
        if snapshot_revision != expectation.revision:
            raise DevstralSnapshotFreezeError(
                "snapshot revision does not match the pinned revision"
            )
        if not freeze_path.is_file():
            raise DevstralSnapshotFreezeError("snapshot freeze record is missing")
        expected = build_devstral_snapshot_freeze(files, expectation=expectation)
        recorded, payload = _load_canonical_record(freeze_path)
        if recorded != expected:
            raise DevstralSnapshotFreezeError(
                "freeze record differs from the observed pinned snapshot identity"
            )
        return DevstralSnapshotFreezeValidation(
            valid=True,
            reason="immutable freeze matches the observed pinned snapshot",
            freeze_sha256=sha256_bytes(payload),
            snapshot_identity_sha256=str(expected["snapshot"]["identity_sha256"]),
        )
    except (DevstralSnapshotFreezeError, OSError, KeyError, TypeError) as error:
        freeze_sha256 = None
        if freeze_path.is_file():
            try:
                freeze_sha256 = sha256_file(freeze_path)
            except OSError:
                pass
        return DevstralSnapshotFreezeValidation(
            valid=False,
            reason=str(error),
            freeze_sha256=freeze_sha256,
        )


def validate_devstral_snapshot_freeze(
    freeze_path: Path,
    snapshot: Path,
    *,
    expectation: DevstralSnapshotExpectation = PINNED_DEVSTRAL_SNAPSHOT,
) -> DevstralSnapshotFreezeValidation:
    """Inspect and validate a snapshot, returning NOT_READY on every failure."""
    try:
        files = observe_devstral_snapshot(snapshot, expectation=expectation)
    except (DevstralSnapshotFreezeError, OSError) as error:
        return DevstralSnapshotFreezeValidation(valid=False, reason=str(error))
    return validate_devstral_snapshot_freeze_observation(
        freeze_path,
        files,
        snapshot_revision=Path(snapshot).name,
        expectation=expectation,
    )


__all__ = [
    "DevstralSnapshotExpectation",
    "DevstralSnapshotFreezeError",
    "DevstralSnapshotFreezeValidation",
    "FREEZE_SCHEMA",
    "PINNED_DEVSTRAL_SNAPSHOT",
    "RUNTIME_WEIGHT_FILE",
    "SNAPSHOT_FREEZE",
    "build_devstral_snapshot_freeze",
    "canonical_json_bytes",
    "create_devstral_snapshot_freeze",
    "observe_devstral_snapshot",
    "sha256_file",
    "validate_devstral_snapshot_freeze",
    "validate_devstral_snapshot_freeze_observation",
    "write_devstral_snapshot_freeze_atomic",
]
