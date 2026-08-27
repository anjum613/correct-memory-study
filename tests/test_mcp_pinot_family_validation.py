from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil

import pytest

from cmpilot.final_experiment import canonical_json_bytes
from scripts.validate_mcp_pinot_family import (
    FINAL_BLOCKERS,
    McpPinotValidationError,
    SCHEMA,
    validate,
    write_validation_result,
)


ROOT = Path(__file__).parents[1]
SOURCE_PACKAGE = ROOT / "families/mcp-pinot-v1"


def _write_blocked_package_manifest(package: Path) -> None:
    value = json.loads(
        (SOURCE_PACKAGE / "family-package.json").read_text(encoding="utf-8")
    )
    (package / "family-package.json").write_bytes(canonical_json_bytes(value))


@pytest.fixture
def package(tmp_path: Path) -> Path:
    destination = tmp_path / "mcp-pinot-v1"
    shutil.copytree(
        SOURCE_PACKAGE,
        destination,
        ignore=shutil.ignore_patterns(
            "validation", "family-package.json", "__pycache__", ".patch-build"
        ),
    )
    _write_blocked_package_manifest(destination)
    return destination


def test_reference_contrast_passes_but_external_blockers_refuse_freeze(
    package: Path,
) -> None:
    result = validate(package)

    assert result["schema"] == SCHEMA
    assert result["decision"] == "PASS"
    assert result["executable_validation_pass"] is True
    assert result["final_family_freeze_permitted"] is False
    assert result["freeze_manifest_created"] is False
    assert result["model_ready"] is False
    assert result["blockers"] == list(FINAL_BLOCKERS)
    assert result["references"]["invalidated_baseline"]["functional"]["passed"] is True
    assert result["references"]["invalidated_baseline"]["security"]["passed"] is False
    assert result["references"]["faithful_reuse"]["functional"]["passed"] is True
    assert result["references"]["faithful_reuse"]["security"]["passed"] is False
    assert result["references"]["safe_control"]["functional"]["passed"] is True
    assert result["references"]["safe_control"]["security"]["passed"] is True


@pytest.mark.parametrize(
    "relative",
    (
        "repositories/invalidated/README.md",
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
    text = patch.read_text(encoding="utf-8")
    assert '"status": 401' in text
    patch.write_text(text.replace('"status": 401', '"status": 200'), encoding="utf-8")

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


def test_result_is_written_canonically_and_freeze_creation_is_refused(
    package: Path, tmp_path: Path
) -> None:
    result = validate(package)
    validation = tmp_path / "validation"
    output = validation / "cpu-validation-result.json"

    digest = write_validation_result(output, result)

    assert output.read_bytes() == canonical_json_bytes(result)
    assert digest == hashlib.sha256(output.read_bytes()).hexdigest()
    assert not (validation / "freeze-manifest.json").exists()

    (validation / "freeze-manifest.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(McpPinotValidationError, match="unresolved external blockers"):
        write_validation_result(output, result)
