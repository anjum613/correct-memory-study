from __future__ import annotations

import os
from pathlib import Path

import pytest

from cmpilot.integrations.miniswe.filesystem_sandbox import run_sandboxed_command


def _environment(root: Path) -> dict[str, str]:
    home = root / "home"
    temporary = root / "tmp"
    home.mkdir()
    temporary.mkdir()
    return {
        "HOME": str(home),
        "PATH": f"{Path(os.sys.executable).parent}:/usr/bin:/bin",
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": str(temporary),
    }


def test_landlock_helper_allows_only_declared_task_paths(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    writable = repository / "writable.txt"
    protected = repository / "protected.txt"
    writable.write_text("old\n", encoding="utf-8")
    protected.write_text("protected\n", encoding="utf-8")
    environment = _environment(tmp_path)
    command = (
        "cat protected.txt; printf 'new\\n' > writable.txt; "
        "printf 'bad\\n' > protected.txt"
    )

    result = run_sandboxed_command(
        command,
        cwd=repository,
        environment=environment,
        readable_roots=[repository],
        writable_files=[writable],
        writable_directories=[Path(environment["HOME"]), Path(environment["TMPDIR"])],
        timeout=10,
    )

    assert result.isolation_established is True
    assert result.diagnostic["landlock_abi"] >= 1
    assert result.returncode != 0
    assert writable.read_text(encoding="utf-8") == "new\n"
    assert protected.read_text(encoding="utf-8") == "protected\n"


def test_sandbox_fails_closed_without_executing_command(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    marker = repository / "must-not-exist"
    environment = _environment(tmp_path)

    result = run_sandboxed_command(
        "touch must-not-exist",
        cwd=repository,
        environment=environment,
        readable_roots=[repository],
        writable_files=[],
        writable_directories=[Path(environment["HOME"]), Path(environment["TMPDIR"])],
        timeout=10,
        minimum_abi=99,
    )

    assert result.isolation_established is False
    assert result.returncode == 125
    assert result.diagnostic["classification"] == "SANDBOX_CAPABILITY_UNAVAILABLE"
    assert not marker.exists()


def test_runtime_created_symlink_cannot_escape_allowed_tmp(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    denied = tmp_path / "denied"
    denied.mkdir()
    (denied / "secret").write_text("secret\n", encoding="utf-8")
    script = repository / "probe.py"
    script.write_text(
        f'''from pathlib import Path
import os

alias = Path(os.environ["TMPDIR"]) / "alias"
alias.symlink_to(Path({str(denied)!r}), target_is_directory=True)
try:
    (alias / "secret").read_text()
except PermissionError:
    raise SystemExit(0)
raise SystemExit(13)
''',
        encoding="utf-8",
    )
    environment = _environment(tmp_path)

    result = run_sandboxed_command(
        "python probe.py",
        cwd=repository,
        environment=environment,
        readable_roots=[repository],
        writable_files=[],
        writable_directories=[Path(environment["HOME"]), Path(environment["TMPDIR"])],
        timeout=10,
    )

    assert result.isolation_established is True
    assert result.returncode == 0
    assert (Path(environment["TMPDIR"]) / "alias").is_symlink()


def test_sandbox_records_abi1_limitations_without_claiming_later_rights(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    environment = _environment(tmp_path)

    result = run_sandboxed_command(
        "true",
        cwd=repository,
        environment=environment,
        readable_roots=[repository],
        writable_files=[],
        writable_directories=[Path(environment["HOME"]), Path(environment["TMPDIR"])],
        timeout=10,
    )

    assert result.returncode == 0
    if result.diagnostic["landlock_abi"] == 1:
        assert result.diagnostic["unsupported_rights"] == [
            "REFER",
            "TRUNCATE",
            "IOCTL_DEV",
        ]
        assert result.diagnostic["abi1_compensating_controls"]["close_fds"] is True
        assert (
            result.diagnostic["abi1_compensating_controls"][
                "private_paths_outside_readable_roots"
            ]
            is True
        )


@pytest.mark.parametrize("alias_kind", ["file", "parent-directory"])
def test_writable_grants_reject_symlink_aliases(
    tmp_path: Path, alias_kind: str
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    denied = tmp_path / "denied"
    denied.mkdir()
    protected = denied / "protected.txt"
    protected.write_text("protected\n", encoding="utf-8")
    environment = _environment(tmp_path)
    if alias_kind == "file":
        alias = repository / "writable.txt"
        alias.symlink_to(protected)
    else:
        alias_parent = repository / "alias"
        alias_parent.symlink_to(denied, target_is_directory=True)
        alias = alias_parent / "protected.txt"

    with pytest.raises(ValueError, match="symlink or symlinked parent"):
        run_sandboxed_command(
            "printf 'changed\\n' > writable.txt",
            cwd=repository,
            environment=environment,
            readable_roots=[repository],
            writable_files=[alias],
            writable_directories=[
                Path(environment["HOME"]), Path(environment["TMPDIR"])
            ],
            timeout=10,
        )

    assert protected.read_text(encoding="utf-8") == "protected\n"
