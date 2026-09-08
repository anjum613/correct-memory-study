from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

import pytest

from cmpilot.final_experiment import canonical_json_bytes
from scripts.validate_djoser_family import (
    FINAL_BLOCKERS,
    SCHEMA,
    validate,
    write_validation_result,
)


ROOT = Path(__file__).parents[1].resolve()


@pytest.fixture
def package(tmp_path: Path) -> Path:
    completed = subprocess.run(
        (
            "git",
            "archive",
            "HEAD",
            "families/djoser-v1",
            "docs/methodology/source-procedural-memory-generation-v1.json",
        ),
        cwd=ROOT,
        check=True,
        capture_output=True,
        timeout=30,
    )
    with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as archive:
        archive.extractall(tmp_path, filter="data")
    return tmp_path / "families/djoser-v1"


def test_reference_contrast_and_source_memory_admit_final_freeze(
    package: Path,
) -> None:
    result = validate(package)

    assert result["schema"] == SCHEMA
    assert result["decision"] == "PASS"
    assert result["executable_validation_pass"] is True
    assert result["final_family_freeze_permitted"] is True
    assert result["freeze_manifest_created"] is True
    assert result["model_ready"] is True
    assert result["blockers"] == list(FINAL_BLOCKERS) == []
    assert result["selection_status"]["status"] == (
        "EXTERNAL_TRACK_B_PROVENANCE_RESOLVED"
    )
    assert result["source_memory"]["pass"] is True
    assert result["source_memory"]["source_grounding_validation"]["result"] == (
        "PASS"
    )
    assert result["references"]["invalidated_baseline"]["functional"]["passed"] is True
    assert result["references"]["invalidated_baseline"]["security"]["passed"] is False
    assert result["references"]["faithful_reuse"]["functional"]["passed"] is True
    assert result["references"]["faithful_reuse"]["security"]["passed"] is False
    assert result["references"]["safe_control"]["functional"]["passed"] is True
    assert result["references"]["safe_control"]["security"]["passed"] is True


@pytest.mark.parametrize(
    "relative",
    (
        "repositories/invalidated/README.rst",
        "oracles/functional/evaluate.py",
    ),
)
def test_digest_tamper_is_rejected(package: Path, relative: str) -> None:
    path = package / relative
    path.write_bytes(path.read_bytes() + b"\n# validation tamper\n")

    result = validate(package)

    assert result["decision"] == "FAIL"
    assert result["executable_validation_pass"] is False
    assert result["family_package"]["pass"] is False
    if relative.startswith("repositories/"):
        assert result["snapshot_provenance"]["pass"] is False


def test_safe_reference_must_establish_the_frozen_contrast(package: Path) -> None:
    patch = package / "references/safe-control/secure.patch"
    patch.write_text(
        """diff --git a/djoser/serializers.py b/djoser/serializers.py
--- a/djoser/serializers.py
+++ b/djoser/serializers.py
@@ -115,6 +115,7 @@ class TokenCreateSerializer(serializers.Serializer):
         password = attrs.get("password")
         params = {settings.LOGIN_FIELD: attrs.get(settings.LOGIN_FIELD)}
         self.user = authenticate(**params, password=password)
+        # Deliberately unsafe tamper: retain the direct fallback below.
         if not self.user:
             self.user = User.objects.filter(**params).first()
             if self.user and not self.user.check_password(password):
""",
        encoding="utf-8",
    )

    result = validate(package)

    assert result["decision"] == "FAIL"
    assert result["references"]["safe_control"]["functional"]["passed"] is True
    assert result["references"]["safe_control"]["security"]["passed"] is False
    assert result["references"]["checks"]["contrast"] is False


def test_repeated_validation_is_canonical_and_deterministic(package: Path) -> None:
    first = validate(package)
    second = validate(package)

    assert first == second
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert first["references"]["checks"]["invalidated_baseline"] is True
    assert first["references"]["invalidated_baseline"]["checks"][
        "functional_deterministic"
    ] is True
    assert first["references"]["invalidated_baseline"]["checks"][
        "security_deterministic"
    ] is True


def test_oracles_witness_and_references_are_outside_agent_repositories(
    package: Path,
) -> None:
    result = validate(package)

    for name in ("invalidated_baseline", "faithful_reuse", "safe_control"):
        assert result["references"][name]["checks"]["external_paths_hidden"] is True
        assert all(result["references"][name]["hidden_locations"].values())
    assert result["task_and_policy"]["checks"]["hidden_functional"] is True
    assert result["task_and_policy"]["checks"]["hidden_security"] is True
    assert result["task_and_policy"]["checks"]["references_inaccessible"] is True


def test_result_and_freeze_manifest_are_written_canonically(
    package: Path, tmp_path: Path
) -> None:
    result = validate(package)
    validation = tmp_path / "validation"
    output = validation / "cpu-validation-result.json"

    digest = write_validation_result(output, result)
    freeze = validation / "freeze-manifest.json"
    freeze_value = json.loads(freeze.read_text(encoding="utf-8"))

    assert output.read_bytes() == canonical_json_bytes(result)
    assert digest == hashlib.sha256(output.read_bytes()).hexdigest()
    assert freeze.read_bytes() == canonical_json_bytes(freeze_value)
    assert freeze_value["classification"] == "DJOSER_FAMILY_FROZEN_MODEL_READY"
    assert freeze_value["admission"]["sha256"] == digest
    assert freeze_value["reference_contrast"] == {
        "faithful_reuse_functional": True,
        "faithful_reuse_security": False,
        "safe_control_functional": True,
        "safe_control_security": True,
    }

    assert write_validation_result(output, result) == digest
    assert freeze.read_bytes() == canonical_json_bytes(freeze_value)
