from __future__ import annotations

import os
from pathlib import Path

from cmpilot.artifact_preserver import (
    atomic_preserve_directory,
    directory_tree_sha256,
)


def test_atomic_preservation_is_idempotent_with_read_only_git_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    git_objects = source / ".git" / "objects" / "ab"
    git_objects.mkdir(parents=True)
    (source / "trajectory.json").write_text('{"complete": true}\n', encoding="utf-8")
    read_only = git_objects / "object"
    read_only.write_bytes(b"immutable object")
    read_only.chmod(0o444)
    destination = tmp_path / "artifacts" / "agent-run"

    first = atomic_preserve_directory(source, destination)
    first_hash = directory_tree_sha256(destination)
    second = atomic_preserve_directory(source, destination)
    second_hash = directory_tree_sha256(destination)

    assert first.status == "preserved"
    assert second.status == "already_preserved"
    assert first.tree_sha256 == second.tree_sha256
    assert first_hash == second_hash
    assert (destination / ".git" / "objects" / "ab" / "object").read_bytes() == b"immutable object"
    assert not (destination / "agent-run").exists()
    assert not list(destination.parent.glob(".agent-run.preserve-*"))
    assert os.access(destination / ".git" / "objects" / "ab" / "object", os.R_OK)
