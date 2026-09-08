from __future__ import annotations

from pathlib import Path

from scripts.build_source_corpus_v2_evidence import (
    S2_SPECS,
    execution_command,
    logical_test_command,
)


def _candidate(path: str, symbol: str) -> dict:
    return {"source_task_provenance": {"path": path, "symbol": symbol}}


def test_runner_commands_are_deterministic_and_node_specific() -> None:
    specs = {
        "pytest": {"test_runner": "PYTEST_NODE"},
        "django": {"test_runner": "DJANGO_RUNTESTS_NODE"},
        "wagtail": {"test_runner": "WAGTAIL_RUNTESTS_NODE"},
        "trial": {"test_runner": "TWISTED_TRIAL_NODE"},
    }
    assert logical_test_command(
        specs["pytest"], _candidate("tests/test_x.py", "TestX.test_one")
    ).endswith("tests/test_x.py::TestX::test_one")
    assert logical_test_command(
        specs["django"], _candidate("tests/utils_tests/test_x.py", "TestX.test_one")
    ) == "python tests/runtests.py utils_tests.test_x.TestX.test_one -v 1"
    assert logical_test_command(
        specs["wagtail"], _candidate("wagtail/core/tests/test_x.py", "TestX.test_one")
    ) == "python runtests.py wagtail.core.tests.test_x.TestX.test_one -v 1"
    assert logical_test_command(
        specs["trial"],
        _candidate("master/buildbot/test/unit/test_x.py", "TestX.test_one"),
    ) == "cd master && python -m twisted.trial buildbot.test.unit.test_x.TestX.test_one"
    starlette = logical_test_command(
        S2_SPECS[1], _candidate("tests/test_authentication.py", "test_one")
    )
    assert "-W ignore::DeprecationWarning" in starlette
    assert starlette.endswith("tests/test_authentication.py::test_one")


def test_s2_materializations_are_exact_frozen_queue_prefix() -> None:
    assert [(spec["repository_url"], spec["anchor"]) for spec in S2_SPECS] == [
        (
            "https://github.com/apache/airflow.git",
            "ac65b82eeeeaa670e09a83c7da65cbac7e89f8db",
        ),
        (
            "https://github.com/encode/starlette.git",
            "1797de464124b090f10cf570441e8292936d63e3",
        ),
        (
            "https://github.com/jtesta/ssh-audit.git",
            "8e972c5e94b460379fe0c7d20209c16df81538a5",
        ),
    ]
    assert all(spec["commit"] != spec["anchor"] for spec in S2_SPECS)
    assert all(Path(spec["license_path"]).is_absolute() is False for spec in S2_SPECS)


def test_s2_execution_changes_to_the_pinned_source_tree(tmp_path: Path) -> None:
    source_tree = tmp_path / "source tree"
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin/python").touch()
    source_tree.mkdir()
    argv, environment = execution_command(
        {"tier": "S2", "venv_path": venv, "pythonpath": "."},
        source_tree,
        "python -m pytest tests/test_example.py",
    )
    assert argv[:2] == ["/bin/bash", "-lc"]
    assert argv[2].startswith(f"cd '{source_tree}' && ")
    assert str(venv / "bin/python") in argv[2]
    assert environment is not None
    assert environment["PYTHONPATH"] == str(source_tree)
