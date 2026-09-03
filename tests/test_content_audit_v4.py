from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3

import pytest

from cmpilot.content_audit_v4 import (
    ArtifactRef,
    ContentAccessAudit,
    ContentAuditV4Error,
    TreeRef,
)
from cmpilot.susvibes_feasibility import tree_sha256


TARGET = "development__audit_" + "a" * 40


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def test_global_audit_records_exact_reads_and_enforces_append_only_chain(
    tmp_path: Path,
) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "task.md").write_bytes(b"implement the feature\n")
    tree = artifacts / "B"
    tree.mkdir()
    (tree / "feature.py").write_bytes(b"VALUE = 1\n")
    audit = ContentAccessAudit(
        tmp_path / "audit.sqlite",
        boundaries={"TARGET": artifacts},
        phase="V4_DEVELOPMENT",
        session_id="test-session",
    )

    payload = audit.read_bytes(
        ArtifactRef("TARGET_TASK", "TARGET", "task.md", _sha(b"implement the feature\n")),
        target_id=TARGET,
        source_id=None,
        caller="test",
    )
    verified_tree = audit.verify_tree(
        TreeRef("TARGET_B", "TARGET", "B", tree_sha256(tree)),
        target_id=TARGET,
        source_id=None,
        caller="test",
    )

    assert payload == b"implement the feature\n"
    assert verified_tree == tree.resolve()
    events = audit.events()
    assert [event["logical_resource"] for event in events] == [
        "TARGET_TASK",
        "TARGET_B:FILE",
        "TARGET_B",
    ]
    assert all(event["allowed_boundary"] == "TARGET" for event in events)
    assert all(event["target_id"] == TARGET for event in events)
    assert audit.verify_chain() == events[-1]["event_sha256"]
    with sqlite3.connect(audit.database) as connection, pytest.raises(
        sqlite3.IntegrityError, match="append-only"
    ):
        connection.execute("DELETE FROM content_access")


def test_tree_audit_prunes_excluded_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifacts = tmp_path / "artifacts"
    tree = artifacts / "B"
    hidden = tree / ".git" / "objects"
    hidden.mkdir(parents=True)
    (tree / "feature.py").write_bytes(b"VALUE = 1\n")
    forbidden = hidden / "large-object"
    forbidden.write_bytes(b"must not be read")
    original_read_bytes = Path.read_bytes

    def guarded_read_bytes(path: Path) -> bytes:
        if path == forbidden:
            raise AssertionError("excluded directory was traversed")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    audit = ContentAccessAudit(
        tmp_path / "audit.sqlite",
        boundaries={"TARGET": artifacts},
        phase="V4_DEVELOPMENT",
    )

    audit.verify_tree(
        TreeRef("TARGET_B", "TARGET", "B", tree_sha256(tree)),
        target_id=TARGET,
        source_id=None,
        caller="test",
    )

    identifiers = [event["content_identifier"] for event in audit.events()]
    assert all(".git" not in identifier for identifier in identifiers)


def test_verified_tree_reader_is_global_and_detects_post_verification_change(
    tmp_path: Path,
) -> None:
    artifacts = tmp_path / "artifacts"
    tree = artifacts / "B"
    tree.mkdir(parents=True)
    target = tree / "feature.py"
    target.write_bytes(b"VALUE = 1\n")
    reference = TreeRef("TARGET_B", "TARGET", "B", tree_sha256(tree))
    audit = ContentAccessAudit(
        tmp_path / "audit.sqlite",
        boundaries={"TARGET": artifacts},
        phase="V4_DEVELOPMENT",
    )
    audit.verify_tree(
        reference, target_id=TARGET, source_id=None, caller="test"
    )

    assert audit.list_verified_tree_files(reference, suffix=".py") == ("feature.py",)
    assert audit.read_verified_tree_file(
        reference,
        "feature.py",
        target_id=TARGET,
        source_id=None,
        caller="matcher",
    ) == b"VALUE = 1\n"
    assert audit.events()[-1]["logical_resource"] == "TARGET_B:VERIFIED_READ"
    target.write_bytes(b"VALUE = 2\n")
    with pytest.raises(ContentAuditV4Error, match="changed after verification"):
        audit.read_verified_tree_file(
            reference,
            "feature.py",
            target_id=TARGET,
            source_id=None,
            caller="matcher",
        )


def test_audit_fails_closed_on_unmediated_types_hash_changes_and_escapes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "value").write_bytes(b"bound")
    audit = ContentAccessAudit(
        tmp_path / "audit.sqlite",
        boundaries={"ROOT": root},
        phase="V4_DEVELOPMENT",
    )
    with pytest.raises(ContentAuditV4Error, match="ArtifactRef"):
        audit.read_bytes(  # type: ignore[arg-type]
            root / "value", target_id=TARGET, source_id=None, caller="test"
        )
    with pytest.raises(ContentAuditV4Error, match="SHA-256 mismatch"):
        audit.read_bytes(
            ArtifactRef("VALUE", "ROOT", "value", "0" * 64),
            target_id=TARGET,
            source_id=None,
            caller="test",
        )
    with pytest.raises(ContentAuditV4Error, match="invalid immutable"):
        ArtifactRef("VALUE", "ROOT", "../value", _sha(b"bound"))
    assert audit.events() == ()


def test_development_binding_is_audited_and_disabled_for_confirmation(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "value").write_bytes(b"bound")
    development = ContentAccessAudit(
        tmp_path / "development.sqlite",
        boundaries={"ROOT": root},
        phase="V4_DEVELOPMENT_ORIGINAL_FIVE",
    )
    ref = development.bind_development_file(
        logical_resource="VALUE",
        boundary="ROOT",
        relative_path="value",
        target_id=TARGET,
        source_id=None,
        caller="test",
    )
    assert ref.sha256 == _sha(b"bound")
    assert development.events()[0]["logical_resource"] == "BINDING:VALUE"
    confirmation = ContentAccessAudit(
        tmp_path / "confirmation.sqlite",
        boundaries={"ROOT": root},
        phase="CONFIRMATORY_SCREENING",
    )
    with pytest.raises(ContentAuditV4Error, match="unavailable in confirmation"):
        confirmation.bind_development_file(
            logical_resource="VALUE",
            boundary="ROOT",
            relative_path="value",
            target_id=TARGET,
            source_id=None,
            caller="test",
        )
