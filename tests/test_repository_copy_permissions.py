from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from cmpilot.repository_manager import (
    WORKING_COPY_PERMISSION_FAILURE,
    RepositoryCopyError,
    classify_working_copy_failure,
    prepare_working_copy,
    repository_content_digest,
    repository_preparation_record,
    run_tests,
)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.lstat().st_mode)


def _external_target_metadata(path: Path) -> tuple[int, ...]:
    information = path.stat()
    return (
        information.st_dev,
        information.st_ino,
        information.st_mode,
        information.st_nlink,
        information.st_uid,
        information.st_gid,
        information.st_size,
        information.st_mtime_ns,
        information.st_ctime_ns,
    )


def _unlink_deliberate_unsafe_fixture(
    link: Path, *, test_directory: Path
) -> None:
    expected = test_directory / "unsafe"
    try:
        link.relative_to(test_directory)
    except ValueError as error:
        raise AssertionError("fixture link is outside its test-owned directory") from error
    if (
        not test_directory.is_absolute()
        or link != expected
        or link.parent != test_directory
    ):
        raise AssertionError("fixture teardown received an unexpected link path")
    if link.is_symlink():
        link.unlink()
    elif os.path.lexists(link):
        raise AssertionError("unsafe fixture link was replaced by a non-symlink")


@contextmanager
def _deliberate_unsafe_symlink(
    test_directory: Path, *, target: str
) -> Iterator[Path]:
    link = test_directory / "unsafe"
    if (
        not test_directory.is_absolute()
        or link.parent != test_directory
        or link != test_directory / "unsafe"
    ):
        raise AssertionError("unsafe fixture path is not lexically test-owned")
    link.symlink_to(target)
    try:
        yield link
    finally:
        _unlink_deliberate_unsafe_fixture(link, test_directory=test_directory)


def _make_template(root: Path) -> dict[Path, bytes]:
    root.mkdir()
    nested = root / "nested"
    nested.mkdir()
    files = {
        Path("calculator.py"): b"def add(left, right):\n    raise NotImplementedError\n",
        Path("nested/data.txt"): b"unchanged bytes\n",
        Path("run-check"): b"#!/bin/sh\nexit 0\n",
    }
    for relative, contents in files.items():
        (root / relative).write_bytes(contents)
    (root / "calculator.py").chmod(0o444)
    (root / "nested/data.txt").chmod(0o400)
    (root / "run-check").chmod(0o555)
    nested.chmod(0o555)
    root.chmod(0o555)
    return files


def _restore_source_directories(source: Path) -> None:
    directories = [
        path
        for path in source.rglob("*")
        if path.is_dir() and not path.is_symlink()
    ]
    for directory in reversed(directories):
        directory.chmod(0o700)
    source.chmod(0o700)


def test_read_only_source_produces_writable_committed_copy(tmp_path: Path) -> None:
    source = tmp_path / "source"
    original = _make_template(source)
    source_modes = {
        path.relative_to(source): _mode(path)
        for path in [source, *source.rglob("*")]
    }
    source_digest = repository_content_digest(source)
    destination = tmp_path / "working-copy"

    try:
        working_copy, commit = prepare_working_copy(source, destination=destination)

        assert working_copy == destination
        assert len(commit) == 40
        assert _mode(source) == 0o555
        assert _mode(destination) == 0o700
        assert _mode(destination / "nested") == 0o700
        assert os.access(destination, os.W_OK | os.X_OK)
        assert (destination / ".git").is_dir()
        assert repository_content_digest(destination) == source_digest
        preparation = repository_preparation_record(source, destination, commit)
        assert preparation["policy"] == "isolated-repository-copy-v1"
        assert preparation["content_digest_match"] is True
        assert preparation["source"]["root_mode"] == "0555"
        assert preparation["destination"]["root_mode"] == "0700"
        assert preparation["git"]["directory_created"] is True
        assert preparation["git"]["status"] == ""
        assert {
            path.relative_to(source): _mode(path)
            for path in [source, *source.rglob("*")]
        } == source_modes
        assert {
            relative: (source / relative).read_bytes() for relative in original
        } == original

        calculator = destination / "calculator.py"
        calculator.write_text("def add(left, right):\n    return left + right\n", encoding="utf-8")
        assert calculator.read_text(encoding="utf-8").endswith("left + right\n")
        assert (source / "calculator.py").read_bytes() == original[Path("calculator.py")]
    finally:
        _restore_source_directories(source)


def test_destination_file_modes_are_normalized_deterministically(tmp_path: Path) -> None:
    source = tmp_path / "source"
    _make_template(source)
    try:
        destination, _ = prepare_working_copy(
            source, destination=tmp_path / "working-copy"
        )

        assert _mode(destination / "calculator.py") == 0o600
        assert _mode(destination / "nested/data.txt") == 0o600
        assert _mode(destination / "run-check") == 0o700
        assert not os.access(destination / "calculator.py", os.X_OK)
        assert os.access(destination / "run-check", os.X_OK)
    finally:
        _restore_source_directories(source)


def test_existing_source_git_directory_is_not_copied(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "calculator.py").write_text("value = 1\n", encoding="utf-8")
    old_git = source / ".git"
    old_git.mkdir()
    (old_git / "prior-run-marker").write_text("must not copy\n", encoding="utf-8")

    destination, _ = prepare_working_copy(
        source, destination=tmp_path / "working-copy"
    )

    assert (destination / ".git").is_dir()
    assert not (destination / ".git/prior-run-marker").exists()
    assert (
        subprocess.run(
            ["git", "-C", str(destination), "status", "--short"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        == ""
    )


def test_safe_relative_symlink_is_preserved(tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "nested").mkdir(parents=True)
    (source / "target.txt").write_text("target\n", encoding="utf-8")
    (source / "nested/link.txt").symlink_to("../target.txt")
    source_digest = repository_content_digest(source)

    destination, _ = prepare_working_copy(
        source, destination=tmp_path / "working-copy"
    )

    copied_link = destination / "nested/link.txt"
    assert copied_link.is_symlink()
    assert os.readlink(copied_link) == "../target.txt"
    assert copied_link.read_text(encoding="utf-8") == "target\n"
    assert repository_content_digest(destination) == source_digest

    _unlink_deliberate_unsafe_fixture(
        source / "unsafe", test_directory=source
    )
    assert copied_link.is_symlink()
    assert (source / "nested/link.txt").is_symlink()


@pytest.mark.parametrize("target", ["../outside.txt", "/etc/passwd"])
def test_external_symlink_is_rejected_and_destination_is_cleaned(
    tmp_path: Path, target: str
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    destination = tmp_path / "working-copy"
    sibling = tmp_path / "preserve-me"
    sibling.write_text("preserved\n", encoding="utf-8")
    external_target = (
        Path("/etc/passwd") if Path(target).is_absolute() else tmp_path / "outside.txt"
    )
    if not Path(target).is_absolute():
        external_target.write_text("external target\n", encoding="utf-8")
    external_before = _external_target_metadata(external_target)
    unsafe_path = source / "unsafe"
    rejection_asserted = False

    with _deliberate_unsafe_symlink(source, target=target) as unsafe:
        assert unsafe == unsafe_path
        assert unsafe.is_symlink()
        assert os.readlink(unsafe) == target
        with pytest.raises(RepositoryCopyError, match="outside"):
            prepare_working_copy(source, destination=destination)
        rejection_asserted = True

        assert unsafe.is_symlink()
        assert not destination.exists()
        assert sibling.read_text(encoding="utf-8") == "preserved\n"
        assert source.is_dir()
        assert _external_target_metadata(external_target) == external_before

    assert rejection_asserted is True
    assert not os.path.lexists(unsafe_path)
    assert _external_target_metadata(external_target) == external_before


def test_unsupported_special_file_fails_and_cleans_only_destination(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    fifo = source / "unsupported.fifo"
    os.mkfifo(fifo)
    destination = tmp_path / "working-copy"

    with pytest.raises(RepositoryCopyError, match="unsupported"):
        prepare_working_copy(source, destination=destination)

    assert not destination.exists()
    assert fifo.exists()


def test_generated_destination_is_removed_after_copy_failure(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    unsafe_path = source / "unsafe"

    with _deliberate_unsafe_symlink(source, target="../outside.txt") as unsafe:
        with pytest.raises(RepositoryCopyError, match="outside"):
            prepare_working_copy(source, temporary_root=tmp_path)

        assert not list(tmp_path.glob("cmpilot-smoke-*"))
        assert source.is_dir()
        assert unsafe.is_symlink()

    assert not os.path.lexists(unsafe_path)


def test_unsafe_fixture_teardown_is_idempotent_after_later_failure(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    unsafe_path = source / "unsafe"

    def fail_after_rejection() -> None:
        with _deliberate_unsafe_symlink(source, target="../outside.txt") as unsafe:
            with pytest.raises(RepositoryCopyError, match="outside"):
                prepare_working_copy(source, destination=tmp_path / "working-copy")
            assert unsafe.is_symlink()
            raise AssertionError("simulated later assertion failure")

    with pytest.raises(AssertionError, match="simulated later assertion failure"):
        fail_after_rejection()

    assert not os.path.lexists(unsafe_path)
    _unlink_deliberate_unsafe_fixture(unsafe_path, test_directory=source)
    assert not os.path.lexists(unsafe_path)


def test_content_digest_ignores_permissions_and_timestamps(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    value = source / "value.txt"
    value.write_bytes(b"stable\n")
    before = repository_content_digest(source)

    value.chmod(0o400)
    source.chmod(0o555)
    os.utime(value, ns=(1_000_000_000, 2_000_000_000))
    try:
        assert repository_content_digest(source) == before
    finally:
        source.chmod(0o700)


def test_job_25514_old_failure_and_corrected_preparation(tmp_path: Path) -> None:
    fixture = {
        "classification": "WORKING_COPY_PERMISSION_FAILURE",
        "destination_mode": 0o555,
        "git_directory_created": False,
        "git_exit_code": 1,
        "source_mode": 0o555,
    }
    source = tmp_path / "source"
    _make_template(source)
    old_destination = tmp_path / "old-copy"
    shutil.copytree(source, old_destination)
    old_git = subprocess.run(
        ["git", "-C", str(old_destination), "init"],
        text=True,
        capture_output=True,
    )
    observed = {
        **fixture,
        "destination_mode": _mode(old_destination),
        "git_directory_created": (old_destination / ".git").exists(),
        "git_exit_code": old_git.returncode,
    }

    try:
        assert classify_working_copy_failure(observed) == fixture["classification"]
        corrected, _ = prepare_working_copy(
            source, destination=tmp_path / "corrected-copy"
        )
        assert _mode(corrected) == 0o700
        assert (corrected / ".git").is_dir()
    finally:
        _restore_source_directories(source)
        old_destination.chmod(0o700)


def test_calculator_preparation_replay_starts_with_three_failures(
    tmp_path: Path,
) -> None:
    original = Path(__file__).parents[1] / "tasks/smoke_test/repository"
    source = tmp_path / "frozen-calculator"
    shutil.copytree(original, source)
    original_bytes = {
        path.relative_to(source): path.read_bytes()
        for path in source.rglob("*")
        if path.is_file()
    }
