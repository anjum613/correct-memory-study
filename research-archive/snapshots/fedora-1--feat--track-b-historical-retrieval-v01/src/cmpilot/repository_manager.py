"""Create and inspect isolated repositories for the engineering smoke test."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def prepare_working_copy(
    template: Path,
    *,
    temporary_root: Path | None = None,
    destination: Path | None = None,
) -> tuple[Path, str]:
    """Copy a template into a fresh repository and create its initial commit."""
    if not template.is_dir():
        raise FileNotFoundError(f"smoke template does not exist: {template}")
    if destination is not None:
        working_copy = destination
        if working_copy.exists():
            raise FileExistsError(f"working-copy destination already exists: {working_copy}")
    else:
        working_copy = Path(tempfile.mkdtemp(prefix="cmpilot-smoke-", dir=temporary_root))

    shutil.copytree(template, working_copy, dirs_exist_ok=True)
    for arguments in (
        ("init",),
        ("config", "user.name", "cmpilot smoke preparer"),
        ("config", "user.email", "cmpilot@example.invalid"),
        ("add", "."),
        ("commit", "-m", "Initial smoke-test repository"),
    ):
        git(working_copy, *arguments, check=True)
    return working_copy, git(working_copy, "rev-parse", "HEAD", check=True).stdout.strip()


def git(repository: Path, *arguments: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        text=True,
        capture_output=True,
        check=check,
    )


def run_tests(repository: Path) -> subprocess.CompletedProcess[str]:
    """Run the template's pytest suite without creating caches in the copy."""
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=repository,
        text=True,
        capture_output=True,
        env=environment,
    )


def template_snapshot(template: Path) -> dict[Path, bytes]:
    return {path.relative_to(template): path.read_bytes() for path in template.rglob("*") if path.is_file()}


def final_patch(repository: Path, initial_commit: str) -> str:
    """Return all tracked changes since the initial state, including agent commits."""
    return git(repository, "diff", "--binary", "--no-ext-diff", initial_commit, "--").stdout
