from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from cmpilot.devstral_snapshot_freeze import (
    RUNTIME_WEIGHT_FILE,
    DevstralSnapshotExpectation,
    create_devstral_snapshot_freeze,
    validate_devstral_snapshot_freeze,
    write_devstral_snapshot_freeze_atomic,
)


METADATA = {
    "config.json": b'{"model_type":"mistral"}\n',
    "generation_config.json": b'{"temperature":0}\n',
    "model.safetensors.index.json": b'{"weight_map":{}}\n',
    "params.json": b'{"dim":1}\n',
    "tekken.json": b'{"version":"test"}\n',
}
WEIGHT = b"synthetic-devstral-weight"
REVISION = "a" * 40


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _expectation() -> DevstralSnapshotExpectation:
    return DevstralSnapshotExpectation(
        model_id="mistralai/Devstral-Small-2507",
        revision=REVISION,
        metadata_sha256=tuple(
            sorted((name, _sha256(content)) for name, content in METADATA.items())
        ),
        runtime_weight_size=len(WEIGHT),
        runtime_weight_sha256=_sha256(WEIGHT),
    )


def _snapshot(
    tmp_path: Path,
    *,
    include_weight: bool = True,
    symlink_weight: bool = False,
) -> Path:
    snapshot = tmp_path / REVISION
    snapshot.mkdir()
    for name, content in METADATA.items():
        (snapshot / name).write_bytes(content)
    if include_weight and symlink_weight:
        archive = tmp_path / "archive"
        archive.mkdir()
        target = archive / RUNTIME_WEIGHT_FILE
        target.write_bytes(WEIGHT)
        (snapshot / RUNTIME_WEIGHT_FILE).symlink_to(target)
    elif include_weight:
        (snapshot / RUNTIME_WEIGHT_FILE).write_bytes(WEIGHT)
    return snapshot


def _freeze(snapshot: Path, freeze: Path) -> bytes:
    record = create_devstral_snapshot_freeze(
        snapshot,
        expectation=_expectation(),
    )
    write_devstral_snapshot_freeze_atomic(freeze, record)
    return freeze.read_bytes()


def test_incomplete_snapshot_is_not_ready(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path, include_weight=False)

    result = validate_devstral_snapshot_freeze(
        tmp_path / "freeze.json", snapshot, expectation=_expectation()
    )

    assert result.status == "NOT_READY"
    assert result.valid is False
    assert "required snapshot file is missing" in result.reason


def test_complete_but_unfrozen_snapshot_is_not_ready(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)

    result = validate_devstral_snapshot_freeze(
        tmp_path / "freeze.json", snapshot, expectation=_expectation()
    )

    assert result.status == "NOT_READY"
    assert result.valid is False
    assert result.reason == "snapshot freeze record is missing"


def test_correct_frozen_snapshot_is_ready(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    freeze = tmp_path / "freeze.json"
    _freeze(snapshot, freeze)

    result = validate_devstral_snapshot_freeze(
        freeze, snapshot, expectation=_expectation()
    )

    assert result.status == "READY"
    assert result.valid is True
    assert result.freeze_sha256 == _sha256(freeze.read_bytes())
    assert result.snapshot_identity_sha256 is not None


def test_changed_runtime_weight_is_not_ready(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    freeze = tmp_path / "freeze.json"
    _freeze(snapshot, freeze)
    (snapshot / RUNTIME_WEIGHT_FILE).write_bytes(b"changed")

    result = validate_devstral_snapshot_freeze(
        freeze, snapshot, expectation=_expectation()
    )

    assert result.status == "NOT_READY"
    assert "snapshot SHA-256 mismatch" in result.reason


def test_changed_metadata_is_not_ready(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    freeze = tmp_path / "freeze.json"
    _freeze(snapshot, freeze)
    (snapshot / "params.json").write_bytes(b'{"dim":2}\n')

    result = validate_devstral_snapshot_freeze(
        freeze, snapshot, expectation=_expectation()
    )

    assert result.status == "NOT_READY"
    assert result.reason == "snapshot SHA-256 mismatch: params.json"


def test_wrong_model_revision_is_not_ready(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    wrong_revision = tmp_path / ("b" * 40)
    snapshot.rename(wrong_revision)

    result = validate_devstral_snapshot_freeze(
        tmp_path / "freeze.json",
        wrong_revision,
        expectation=_expectation(),
    )

    assert result.status == "NOT_READY"
    assert "does not match the pinned revision" in result.reason


def test_corrupted_freeze_record_is_not_ready(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    freeze = tmp_path / "freeze.json"
    freeze.write_bytes(b"not-json\n")

    result = validate_devstral_snapshot_freeze(
        freeze, snapshot, expectation=_expectation()
    )

    assert result.status == "NOT_READY"
    assert result.reason == "freeze record is not valid JSON"


def test_symlinked_runtime_weight_is_content_valid(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path, symlink_weight=True)
    freeze = tmp_path / "freeze.json"
    _freeze(snapshot, freeze)

    result = validate_devstral_snapshot_freeze(
        freeze, snapshot, expectation=_expectation()
    )

    assert (snapshot / RUNTIME_WEIGHT_FILE).is_symlink()
    assert result.status == "READY"
    assert str((snapshot / RUNTIME_WEIGHT_FILE).resolve()) not in freeze.read_text()


def test_freeze_record_cannot_be_silently_replaced(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    freeze = tmp_path / "freeze.json"
    original = _freeze(snapshot, freeze)
    record = create_devstral_snapshot_freeze(
        snapshot,
        expectation=_expectation(),
    )

    with pytest.raises(FileExistsError, match="freeze output already exists"):
        write_devstral_snapshot_freeze_atomic(freeze, record)

    assert freeze.read_bytes() == original
