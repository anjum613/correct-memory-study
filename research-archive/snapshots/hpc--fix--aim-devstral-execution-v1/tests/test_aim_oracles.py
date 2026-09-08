from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

import pytest


ROOT = Path(__file__).parents[1]
FAMILY = ROOT / "families/aim-v1"
INVALIDATED = FAMILY / "repositories/invalidated"
PATCH = FAMILY / "references/safe-control/secure.patch"
PROBE_PATH = FAMILY / "oracles/probe_support.py"


def _load_probe_module() -> Any:
    specification = importlib.util.spec_from_file_location(
        "cmpilot_test_aim_probe_support", PROBE_PATH
    )
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    saved_dont_write_bytecode = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        specification.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = saved_dont_write_bytecode
    return module


@pytest.fixture(scope="module")
def probe() -> Any:
    return _load_probe_module()


@pytest.fixture
def safe_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "repository"
    shutil.copytree(INVALIDATED, repository)
    subprocess.run(
        ["git", "apply", str(PATCH)],
        cwd=repository,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return repository


def test_invalidated_revision_is_functional_but_fails_witness(probe: Any) -> None:
    functional = probe.run_probe("functional", INVALIDATED, 5.0)
    security = probe.run_probe("security", INVALIDATED, 5.0)

    assert functional["complete"] is True
    assert functional["passed"] is True
    assert all(functional["checks"].values())
    assert security["complete"] is True
    assert security["passed"] is False
    assert not any(security["checks"].values())


def test_safe_control_preserves_functionality_and_passes_witness(
    probe: Any, safe_repository: Path
) -> None:
    functional = probe.run_probe("functional", safe_repository, 5.0)
    security = probe.run_probe("security", safe_repository, 5.0)

    assert functional["complete"] is True
    assert functional["passed"] is True
    assert all(functional["checks"].values())
    assert security["complete"] is True
    assert security["passed"] is True
    assert all(security["checks"].values())


@pytest.mark.parametrize("reference", ["invalidated", "safe"])
def test_oracle_results_are_deterministic(
    probe: Any, safe_repository: Path, reference: str
) -> None:
    repository = INVALIDATED if reference == "invalidated" else safe_repository
    first = {
        "functional": probe.run_probe("functional", repository, 5.0),
        "security": probe.run_probe("security", repository, 5.0),
    }
    second = {
        "functional": probe.run_probe("functional", repository, 5.0),
        "security": probe.run_probe("security", repository, 5.0),
    }
    assert first == second


@pytest.mark.parametrize("timeout", [0.0, -1.0, 30.1])
def test_probe_rejects_invalid_timeout(probe: Any, timeout: float) -> None:
    result = probe.run_probe("functional", INVALIDATED, timeout)
    assert result["complete"] is False
    assert result["passed"] is False
