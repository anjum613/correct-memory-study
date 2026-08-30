from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

from cmpilot.final_experiment import FROZEN, PRODUCTION, canonical_json_bytes
from cmpilot.final_runtime_backends import SCIENTIFIC_BACKENDS
from cmpilot.flask_cors_backend import (
    FLASK_CORS_BACKEND_ID,
    FLASK_CORS_PACKAGE_LOGICAL_PATH,
    FLASK_CORS_SOURCE_REVISION,
    FLASK_CORS_TARGET_REVISION,
    FlaskCORSBackendError,
    build_flask_cors_backend,
)
from scripts.validate_flask_cors_family import (
    BLOCKERS,
    REJECTION_STATUS,
    SCHEMA,
    validate,
)


ROOT = Path(__file__).parents[1]
SOURCE_PACKAGE = ROOT / "families/flask-cors-v1"


@pytest.fixture
def package(tmp_path: Path) -> Path:
    destination = tmp_path / "flask-cors-v1"
    shutil.copytree(
        SOURCE_PACKAGE,
        destination,
        ignore=shutil.ignore_patterns("validation", "__pycache__"),
    )
    return destination


def test_scaffolding_passes_but_family_is_rejected(package: Path) -> None:
    result = validate(package)

    assert result["schema"] == SCHEMA
    assert result["decision"] == "REJECTED"
    assert result["status"] == REJECTION_STATUS
    assert result["executable_scaffolding_pass"] is True
    assert result["family_freeze_permitted"] is False
    assert result["freeze_manifest_created"] is False
    assert result["model_ready"] is False
    assert result["blockers"] == list(BLOCKERS)
    assert result["p_star"] == {
        "compatible": True,
        "invalidated": False,
        "source": True,
    }
    assert result["reference_contrast"] == {
        "faithful_reuse_functional": True,
        "faithful_reuse_security": True,
        "safe_control_functional": True,
        "safe_control_security": True,
    }


def test_rejected_memory_attempt_cannot_be_treatment(package: Path) -> None:
    status_path = package / "memories/memory-status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    rejection_path = package / "memories/rejected-attempt-1/rejection.json"
    rejection = json.loads(rejection_path.read_text(encoding="utf-8"))

    assert status_path.read_bytes() == canonical_json_bytes(status)
    assert status["status"] == REJECTION_STATUS
    assert status["final_treatment_eligible"] is False
    assert status["regeneration_permitted_within_expansion_attempt"] is False
    assert status["replacement_generated"] is False
    assert rejection_path.read_bytes() == canonical_json_bytes(rejection)
    assert rejection["status"] == REJECTION_STATUS
    assert rejection["regeneration_performed"] is False
    assert rejection["regeneration_permitted_within_expansion_attempt"] is False
    assert validate(package)["scaffolding_checks"]["memory_rejected"] is True


def test_repeated_validation_is_deterministic(package: Path) -> None:
    first = validate(package)
    second = validate(package)

    assert first == second
    assert canonical_json_bytes(first) == canonical_json_bytes(second)


def test_snapshot_tamper_is_rejected(package: Path) -> None:
    readme = package / "repositories/invalidated/README.rst"
    readme.write_bytes(readme.read_bytes() + b"\nvalidation tamper\n")

    result = validate(package)

    assert result["decision"] == "FAIL"
    assert result["executable_scaffolding_pass"] is False
    assert result["snapshot_checks"]["invalidated"]["snapshot"] is False
    assert result["scaffolding_checks"]["package_inputs"] is False


def test_backend_is_registered_but_refuses_blocked_package() -> None:
    package_sha256 = hashlib.sha256(
        (SOURCE_PACKAGE / "family-package.json").read_bytes()
    ).hexdigest()
    context = {
        "family_manifest": {
            "family_id": FLASK_CORS_BACKEND_ID,
            "source_revision": FLASK_CORS_SOURCE_REVISION,
            "target_revision": FLASK_CORS_TARGET_REVISION,
            "task_environment": {
                "path": FLASK_CORS_PACKAGE_LOGICAL_PATH,
                "sha256": package_sha256,
            },
            "task_specification": {"runtime_backend_id": FLASK_CORS_BACKEND_ID},
        },
        "run": {
            "experiment_purpose": PRODUCTION,
            "manifest_freeze_status": FROZEN,
            "target_revision": FLASK_CORS_TARGET_REVISION,
            "task_environment_sha256": package_sha256,
        },
    }

    assert SCIENTIFIC_BACKENDS[FLASK_CORS_BACKEND_ID] is build_flask_cors_backend
    with pytest.raises(
        FlaskCORSBackendError,
        match="refuses a non-FROZEN family package",
    ):
        build_flask_cors_backend(context)
