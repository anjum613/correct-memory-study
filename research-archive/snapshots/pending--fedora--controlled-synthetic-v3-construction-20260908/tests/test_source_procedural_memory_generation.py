from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cmpilot.final_experiment import canonical_json_bytes
from cmpilot.repository_manager import repository_content_digest
from scripts.generate_source_procedural_memory import (
    GENERATOR_ID,
    INPUT_SCHEMA,
    PROTOCOL_ID,
    PROTOCOL_SCHEMA,
    VALIDATION_SCHEMA,
    SourceMemoryGenerationError,
    generate,
)


REVISION = "a" * 40
TREE = "b" * 40


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict[str, object]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))
    return _sha256(path)


def _fixture(tmp_path: Path) -> dict[str, Path | str]:
    repository = tmp_path / "repository"
    source = repository / "source"
    source.mkdir(parents=True)
    implementation = source / "service.py"
    implementation.write_text("def run():\n    return 'source'\n", encoding="utf-8")
    metadata = source / "pyproject.toml"
    metadata.write_text(
        '[project.scripts]\nexample = "service:run"\n', encoding="utf-8"
    )
    source_sha256 = repository_content_digest(source).sha256

    generator_path = Path(__file__).parents[1] / "scripts" / (
        "generate_source_procedural_memory.py"
    )
    protocol = repository / "protocol.json"
    protocol_sha256 = _write_json(
        protocol,
        {
            "generator": {
                "identity": GENERATOR_ID,
                "implementation_sha256": _sha256(generator_path),
            },
            "protocol_id": PROTOCOL_ID,
            "schema": PROTOCOL_SCHEMA,
        },
    )
    validation = repository / "validation.json"
    validation_sha256 = _write_json(
        validation,
        {
            "commands": [
                {
                    "argv": ["pytest", "-q"],
                    "cwd": "source",
                    "exit_code": 0,
                    "stderr_sha256": hashlib.sha256(b"").hexdigest(),
                    "stdout_sha256": hashlib.sha256(b"1 passed\n").hexdigest(),
                }
            ],
            "schema": VALIDATION_SCHEMA,
            "source_repository_sha256": source_sha256,
            "source_revision": REVISION,
            "summary": {"failed": 0, "passed": 1, "skipped": 0, "status": "PASS"},
        },
    )
    bundle = repository / "input.json"
    _write_json(
        bundle,
        {
            "generated_at_utc": "2026-08-28T00:00:00Z",
            "protocol": {
                "commit": "c" * 40,
                "path": "protocol.json",
                "protocol_id": PROTOCOL_ID,
                "sha256": protocol_sha256,
            },
            "schema": INPUT_SCHEMA,
            "source_repository": {
                "path": "source",
                "repository_identity": "example/source",
                "revision": REVISION,
                "sha256": source_sha256,
                "snapshot_sha256": "d" * 64,
                "tree": TREE,
            },
            "source_solution": {
                "artifacts": [
                    {
                        "path": "service.py",
                        "role": "declared project entry point",
                        "selection_evidence": {
                            "exact_text": 'example = "service:run"',
                            "path": "pyproject.toml",
                            "sha256": _sha256(metadata),
                        },
                        "sha256": _sha256(implementation),
                    }
                ],
                "establishment_mode": "HISTORICAL_SOURCE_REVISION",
                "revision": REVISION,
            },
            "source_task": {
                "identity": "Initial source task",
                "kind": "GIT_COMMIT",
                "revision": REVISION,
                "source_only": True,
            },
            "source_validation": {
                "path": "validation.json",
                "sha256": validation_sha256,
            },
        },
    )
    return {
        "bundle": bundle,
        "memory": repository / "memory.md",
        "protocol": protocol,
        "protocol_sha256": protocol_sha256,
        "provenance": repository / "provenance.json",
        "repository": repository,
        "source": source,
    }


def _generate(paths: dict[str, Path | str]) -> dict[str, object]:
    return generate(
        repository_root=Path(paths["repository"]),
        protocol_path=Path(paths["protocol"]),
        expected_protocol_sha256=str(paths["protocol_sha256"]),
        input_path=Path(paths["bundle"]),
        source_root=Path(paths["source"]),
        memory_output=Path(paths["memory"]),
        provenance_output=Path(paths["provenance"]),
    )


def test_deterministic_source_only_generation(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)

    result = _generate(paths)

    memory = Path(paths["memory"]).read_text(encoding="utf-8")
    provenance = json.loads(Path(paths["provenance"]).read_text(encoding="utf-8"))
    assert "def run():" in memory
    assert "target" not in memory.casefold()
    assert result["source_grounding_validation"] == "PASS"
    assert provenance["generation"]["model"] is None
    assert provenance["generation"]["seed"] is None
    assert provenance["generation"]["regeneration_performed"] is False
    assert provenance["source_grounding_validation"]["result"] == "PASS"
    assert Path(paths["provenance"]).read_bytes() == canonical_json_bytes(provenance)


def test_source_artifact_tamper_is_rejected(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    (Path(paths["source"]) / "service.py").write_text(
        "def run():\n    return 'changed'\n", encoding="utf-8"
    )

    with pytest.raises(SourceMemoryGenerationError, match="snapshot changed"):
        _generate(paths)


def test_forbidden_target_input_is_rejected(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    bundle_path = Path(paths["bundle"])
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bundle["target_revision"] = "f" * 40
    bundle_path.write_bytes(canonical_json_bytes(bundle))

    with pytest.raises(SourceMemoryGenerationError, match="forbidden future/target"):
        _generate(paths)


def test_outputs_are_never_overwritten(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    _generate(paths)

    with pytest.raises(SourceMemoryGenerationError, match="refusing to overwrite"):
        _generate(paths)
