"""Prepare an isolated Git working copy of the smoke-test repository."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


DEFAULT_TEMPLATE = Path(__file__).parents[1] / "tasks" / "smoke_test" / "repository"


def prepare_working_copy(
    template: Path = DEFAULT_TEMPLATE,
    *,
    temporary_root: Path | None = None,
) -> tuple[Path, str]:
    """Copy a template into a fresh temporary directory and commit it."""
    working_copy = Path(
        tempfile.mkdtemp(prefix="cmpilot-smoke-", dir=temporary_root)
    )
    shutil.copytree(template, working_copy, dirs_exist_ok=True)

    _run_git(working_copy, "init")
    _run_git(working_copy, "config", "user.name", "cmpilot smoke preparer")
    _run_git(working_copy, "config", "user.email", "cmpilot@example.invalid")
    _run_git(working_copy, "add", ".")
    _run_git(working_copy, "commit", "-m", "Initial smoke-test repository")
    commit_hash = _run_git(working_copy, "rev-parse", "HEAD").stdout.strip()
    return working_copy, commit_hash


def _run_git(working_copy: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(working_copy), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


def main() -> int:
    working_copy, commit_hash = prepare_working_copy()
    print(f"Working copy: {working_copy}")
    print(f"Initial commit: {commit_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
