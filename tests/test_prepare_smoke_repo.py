from __future__ import annotations

from pathlib import Path

from scripts.prepare_smoke_repo import prepare_working_copy
from cmpilot.repository_manager import git, run_tests


def test_prepare_working_copy_creates_committed_copy_without_changing_template(
    tmp_path: Path,
) -> None:
    template = Path(__file__).parents[1] / "tasks" / "smoke_test" / "repository"
    original_contents = {
        path.relative_to(template): path.read_bytes()
        for path in template.rglob("*")
        if path.is_file()
    }

    working_copy, commit_hash = prepare_working_copy(template, temporary_root=tmp_path)

    assert working_copy.parent == tmp_path
    assert (working_copy / "calculator.py").read_bytes() == original_contents[
        Path("calculator.py")
    ]
    assert len(commit_hash) == 40
    assert git(working_copy, "rev-parse", "HEAD", check=True).stdout.strip() == commit_hash
    assert {
        path.relative_to(template): path.read_bytes()
        for path in template.rglob("*")
        if path.is_file()
    } == original_contents


def test_clean_working_copy_tests_initially_fail_from_not_implemented(tmp_path: Path) -> None:
    template = Path(__file__).parents[1] / "tasks" / "smoke_test" / "repository"
    working_copy, _ = prepare_working_copy(template, temporary_root=tmp_path)

    result = run_tests(working_copy)

    assert result.returncode != 0
    assert "NotImplementedError" in result.stdout + result.stderr
