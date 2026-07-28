"""Prepare an isolated Git working copy of the smoke-test repository."""

from __future__ import annotations

from pathlib import Path

from cmpilot.repository_manager import prepare_working_copy


DEFAULT_TEMPLATE = Path(__file__).parents[1] / "tasks" / "smoke_test" / "repository"


def main() -> int:
    working_copy, commit_hash = prepare_working_copy(DEFAULT_TEMPLATE)
    print(f"Working copy: {working_copy}")
    print(f"Initial commit: {commit_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
