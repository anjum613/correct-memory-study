from __future__ import annotations

import os
from pathlib import Path

from cmpilot.environment_content_digest import (
    CONTENT_CHANGED,
    CONTENT_UNCHANGED_METADATA_DIFFERED,
    CONTENT_DIGEST_SCHEMA,
    collect_content_records,
    classify_content_comparison,
    fingerprint_content,
    fingerprint_recorded_distribution_snapshot,
    observe_metadata,
)


HISTORICAL_ROOT = Path(
    "/home/s224049759/run-artifacts/guided-backend-fix/25264/forensics"
)
HISTORICAL_FILES = HISTORICAL_ROOT / "installed-package-files.json"
HISTORICAL_SUMMARY = HISTORICAL_ROOT / "installed-package-summary.json"


def _digest(root: Path, relative_paths: list[str]):
    return fingerprint_content(
        collect_content_records(root, relative_paths),
        packages=[{"name": "Example_Package", "version": "1.2.3"}],
        profile="pytest-environment",
    )


def test_content_digest_ignores_mtime_and_reports_metadata_separately(
    tmp_path: Path,
) -> None:
    path = tmp_path / "module.py"
    path.write_bytes(b"value = 1\n")
    before_digest = _digest(tmp_path, ["module.py"])
    before_metadata = observe_metadata(tmp_path, ["module.py"])

    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10_000_000_000))
    after_digest = _digest(tmp_path, ["module.py"])
    after_metadata = observe_metadata(tmp_path, ["module.py"])

    assert before_digest.sha256 == after_digest.sha256
    assert before_metadata != after_metadata
    assert before_metadata["authoritative"] is False


def test_content_digest_ignores_inode_and_enumeration_order(tmp_path: Path) -> None:
    first = tmp_path / "a.py"
    second = tmp_path / "b.py"
    first.write_bytes(b"a\n")
    second.write_bytes(b"b\n")
    original_inode = first.stat().st_ino
    before_records = collect_content_records(tmp_path, ["a.py", "b.py"])
    replacement = tmp_path / "replacement.py"
    replacement.write_bytes(first.read_bytes())
    os.replace(replacement, first)
    after_records = collect_content_records(tmp_path, ["b.py", "a.py"])

    assert first.stat().st_ino != original_inode
    assert fingerprint_content(before_records, profile="test").sha256 == (
        fingerprint_content(reversed(after_records), profile="test").sha256
    )


def test_content_digest_changes_for_file_bytes(tmp_path: Path) -> None:
    path = tmp_path / "module.py"
    path.write_bytes(b"before\n")
    before = _digest(tmp_path, ["module.py"])
    path.write_bytes(b"after\n")
    after = _digest(tmp_path, ["module.py"])
    assert before.sha256 != after.sha256


def test_content_digest_changes_for_package_version() -> None:
    entries = [{"path": "lib/module.py", "sha256": "0" * 64, "type": "file"}]
    before = fingerprint_content(
        entries, packages=[{"name": "demo", "version": "1"}], profile="test"
    )
    after = fingerprint_content(
        entries, packages=[{"name": "demo", "version": "2"}], profile="test"
    )
    assert before.sha256 != after.sha256


def test_content_digest_changes_for_symlink_target(tmp_path: Path) -> None:
    (tmp_path / "one").write_bytes(b"same\n")
    (tmp_path / "two").write_bytes(b"same\n")
    link = tmp_path / "current"
    link.symlink_to("one")
    before = _digest(tmp_path, ["current"])
    link.unlink()
    link.symlink_to("two")
    after = _digest(tmp_path, ["current"])
    assert before.sha256 != after.sha256


def test_content_digest_changes_when_required_file_is_added_or_removed(
    tmp_path: Path,
) -> None:
    (tmp_path / "one").write_bytes(b"one\n")
    (tmp_path / "two").write_bytes(b"two\n")
    one = _digest(tmp_path, ["one"])
    two = _digest(tmp_path, ["one", "two"])
    removed = _digest(tmp_path, ["two"])
    assert len({one.sha256, two.sha256, removed.sha256}) == 3


def test_canonical_content_record_contains_schema_marker() -> None:
    result = fingerprint_content([], profile="empty")
    assert result.schema == CONTENT_DIGEST_SCHEMA
    assert b'"schema":"environment-content-digest-v1"' in result.canonical_inventory


def test_recorded_579_package_files_have_unchanged_content_digest() -> None:
    assert HISTORICAL_FILES.is_file()
    assert HISTORICAL_SUMMARY.is_file()

    historical = fingerprint_recorded_distribution_snapshot(
        HISTORICAL_FILES, HISTORICAL_SUMMARY, read_current_bytes=False
    )
    current = fingerprint_recorded_distribution_snapshot(
        HISTORICAL_FILES, HISTORICAL_SUMMARY, read_current_bytes=True
    )

    assert historical.entry_count == 579
    assert current.entry_count == 579
    assert historical.package_count == 4
    assert historical.sha256 == current.sha256
    classification = classify_content_comparison(
        historical.as_record(), current.as_record(), metadata_differed=True
    )
    assert classification["label"] == CONTENT_UNCHANGED_METADATA_DIFFERED
    assert classification["authoritative_content_matches"] is True


def test_content_change_overrides_metadata_observation() -> None:
    expected = fingerprint_content([], profile="test").as_record()
    actual = fingerprint_content(
        [{"path": "added", "sha256": "0" * 64, "type": "file"}],
        profile="test",
    ).as_record()
    classification = classify_content_comparison(
        expected, actual, metadata_differed=False
    )
    assert classification["label"] == CONTENT_CHANGED
    assert classification["authoritative_content_matches"] is False
