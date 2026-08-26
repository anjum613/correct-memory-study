from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from cmpilot.devstral_profile import (
    CANDIDATE_LOCK,
    CANDIDATE_LOCK_SHA256,
    CANDIDATE_PACKAGE_VERSIONS,
    CANDIDATE_PYTHON_VERSION,
    ENVIRONMENT_PATH,
    MODEL_SNAPSHOT,
    SERVER_PYTHON,
    validate_candidate_environment,
)
from cmpilot.qualification import MODEL_SNAPSHOT as QWEN_MODEL_SNAPSHOT
from cmpilot.qualification import VLLM_PYTHON as QWEN_VLLM_PYTHON


ROOT = Path(__file__).parents[1]


def test_devstral_paths_are_isolated_from_validated_qwen_runtime() -> None:
    assert SERVER_PYTHON != QWEN_VLLM_PYTHON
    assert ENVIRONMENT_PATH != QWEN_VLLM_PYTHON.parent.parent
    assert MODEL_SNAPSHOT != QWEN_MODEL_SNAPSHOT
    assert "devstral" in str(ENVIRONMENT_PATH).lower()
    assert "Devstral-Small-2507" in str(MODEL_SNAPSHOT)


def test_direct_candidate_pins_are_exact_and_mismatches_fail() -> None:
    candidate = dict(CANDIDATE_PACKAGE_VERSIONS)

    assert validate_candidate_environment(
        python_version=CANDIDATE_PYTHON_VERSION,
        package_versions=candidate,
    ) == ()
    errors = validate_candidate_environment(
        python_version="3.12.8",
        package_versions={**candidate, "vllm": "0.6.1.post2"},
    )
    assert "python: expected 3.11.11, found 3.12.8" in errors
    assert "vllm: expected 0.10.0, found 0.6.1.post2" in errors


def test_candidate_lock_contains_only_the_recorded_direct_pins() -> None:
    lock = ROOT / CANDIDATE_LOCK
    import hashlib

    assert hashlib.sha256(lock.read_bytes()).hexdigest() == CANDIDATE_LOCK_SHA256
    requirements = {
        line.split("==", 1)[0]: line.split("==", 1)[1]
        for line in lock.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    }
    assert requirements == dict(CANDIDATE_PACKAGE_VERSIONS)


def test_environment_verifier_fails_closed_before_staging() -> None:
    completed = subprocess.run(
        (sys.executable, str(ROOT / "scripts/verify_devstral_environment.py")),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"},
        timeout=60,
    )

    assert completed.returncode == 1
    result = json.loads(completed.stdout)
    assert result["status"] == "NOT_READY"
    assert result["production_ready"] is False
    assert result["checks"]["environment_identity_frozen"] is False
    assert result["checks"]["snapshot_identity_frozen"] is False
