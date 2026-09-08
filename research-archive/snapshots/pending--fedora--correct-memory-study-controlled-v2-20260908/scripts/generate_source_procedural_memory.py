#!/usr/bin/env python3
"""Render and freeze procedural memory from source-only evidence.

The renderer is deliberately extractive and non-model-based.  It copies exact
source solution artifacts into a fixed Markdown form after verifying the
frozen protocol, source snapshot, selection evidence, and source-visible
validation record.  It never reads a target repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.final_experiment import canonical_json_bytes  # noqa: E402
from cmpilot.repository_manager import repository_content_digest  # noqa: E402


PROTOCOL_SCHEMA = "cmpilot-source-procedural-memory-generation-protocol-v1"
PROTOCOL_ID = "source-procedural-memory-generation-v1"
INPUT_SCHEMA = "cmpilot-source-procedural-memory-input-v1"
VALIDATION_SCHEMA = "cmpilot-source-visible-validation-v1"
PROVENANCE_SCHEMA = "cmpilot-source-procedural-memory-provenance-v1"
GENERATOR_ID = "cmpilot-deterministic-source-excerpt-renderer-v1"
ESTABLISHMENT_MODES = frozenset(
    {"AUTHORITATIVE_PRIOR_SOURCE_RESULT", "HISTORICAL_SOURCE_REVISION"}
)
FORBIDDEN_INPUT_KEYS = frozenset(
    {
        "advisory",
        "compatible_repository",
        "compatible_revision",
        "expected_target_vulnerability",
        "faithful_reuse",
        "memory_outcomes",
        "safe_control",
        "security_witness",
        "target_model_behavior",
        "target_model_behaviour",
        "target_repository",
        "target_revision",
        "target_task",
    }
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REVISION = re.compile(r"^[0-9a-f]{40}$")


class SourceMemoryGenerationError(ValueError):
    """The source-only generation bundle or requested output is invalid."""


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _load_canonical_object(path: Path, *, label: str) -> tuple[dict[str, Any], str]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SourceMemoryGenerationError(f"cannot read {label}: {path}: {error}") from error
    if not isinstance(value, dict):
        raise SourceMemoryGenerationError(f"{label} must be a JSON object")
    if payload != canonical_json_bytes(value):
        raise SourceMemoryGenerationError(f"{label} must be canonical JSON: {path}")
    return value, _sha256(payload)


def _require_exact_keys(value: Mapping[str, Any], keys: set[str], *, label: str) -> None:
    if set(value) != keys:
        raise SourceMemoryGenerationError(
            f"{label} keys differ: expected={sorted(keys)}, actual={sorted(value)}"
        )


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SourceMemoryGenerationError(f"{label} must be an object")
    return value


def _text(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SourceMemoryGenerationError(f"{label} must be non-empty text")
    return value


def _expected_sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise SourceMemoryGenerationError(f"{label} must be a lowercase SHA-256")
    return value


def _revision(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _REVISION.fullmatch(value):
        raise SourceMemoryGenerationError(f"{label} must be an immutable Git revision")
    return value


def _relative_file(root: Path, value: Any, *, label: str) -> Path:
    text = _text(value, label=label)
    relative = Path(text)
    if relative.is_absolute() or ".." in relative.parts:
        raise SourceMemoryGenerationError(f"{label} must stay inside its source root")
    candidate = root / relative
    if candidate.is_symlink() or not candidate.is_file():
        raise SourceMemoryGenerationError(f"{label} is not a regular source file")
    try:
        candidate.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise SourceMemoryGenerationError(f"{label} escapes its source root") from error
    return candidate


def _repository_relative(repository_root: Path, path: Path, *, label: str) -> str:
    try:
        return path.resolve().relative_to(repository_root.resolve(strict=True)).as_posix()
    except (OSError, ValueError) as error:
        raise SourceMemoryGenerationError(f"{label} must be inside the repository") from error


def _display_path(repository_root: Path, path: Path) -> str:
    """Prefer a repository-relative identity while supporting isolated tests."""

    try:
        return path.resolve(strict=True).relative_to(
            repository_root.resolve(strict=True)
        ).as_posix()
    except ValueError:
        return str(path.resolve(strict=True))


def _reject_forbidden_keys(value: Any, *, location: str = "input") -> None:
    if isinstance(value, Mapping):
        forbidden = sorted(set(value) & FORBIDDEN_INPUT_KEYS)
        if forbidden:
            raise SourceMemoryGenerationError(
                f"forbidden future/target fields at {location}: {forbidden}"
            )
        for key, item in value.items():
            _reject_forbidden_keys(item, location=f"{location}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_forbidden_keys(item, location=f"{location}[{index}]")


def _normalized_source_text(path: Path, *, label: str) -> str:
    try:
        payload = path.read_bytes()
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SourceMemoryGenerationError(f"{label} must be UTF-8") from error
    if b"\r" in payload:
        raise SourceMemoryGenerationError(f"{label} must use LF line endings")
    if unicodedata.normalize("NFC", text) != text:
        raise SourceMemoryGenerationError(f"{label} must already be Unicode NFC")
    if "````" in text:
        raise SourceMemoryGenerationError(f"{label} contains the frozen fence marker")
    return text.rstrip("\n") + "\n"


def _validate_protocol(
    path: Path, *, expected_sha256: str
) -> tuple[dict[str, Any], str]:
    protocol, observed_sha256 = _load_canonical_object(path, label="protocol")
    if observed_sha256 != _expected_sha256(
        expected_sha256, label="expected protocol SHA-256"
    ):
        raise SourceMemoryGenerationError("protocol SHA-256 does not match")
    if protocol.get("schema") != PROTOCOL_SCHEMA:
        raise SourceMemoryGenerationError("unsupported source-memory protocol schema")
    if protocol.get("protocol_id") != PROTOCOL_ID:
        raise SourceMemoryGenerationError("unsupported source-memory protocol identity")
    generator = _mapping(protocol.get("generator"), label="protocol.generator")
    if generator.get("identity") != GENERATOR_ID:
        raise SourceMemoryGenerationError("protocol names a different generator")
    implementation_sha256 = _expected_sha256(
        generator.get("implementation_sha256"),
        label="protocol generator implementation SHA-256",
    )
    if implementation_sha256 != _sha256(Path(__file__).resolve(strict=True).read_bytes()):
        raise SourceMemoryGenerationError("generator implementation SHA-256 changed")
    return protocol, observed_sha256


def _validate_source_validation(
    repository_root: Path,
    source_root: Path,
    record: Mapping[str, Any],
    *,
    source_revision: str,
    source_repository_sha256: str,
) -> tuple[Mapping[str, Any], str, str]:
    _require_exact_keys(record, {"path", "sha256"}, label="source_validation")
    validation_path = _relative_file(
        repository_root, record.get("path"), label="source_validation.path"
    )
    validation, observed_sha256 = _load_canonical_object(
        validation_path, label="source validation record"
    )
    if observed_sha256 != _expected_sha256(
        record.get("sha256"), label="source_validation.sha256"
    ):
        raise SourceMemoryGenerationError("source validation record SHA-256 changed")
    if validation.get("schema") != VALIDATION_SCHEMA:
        raise SourceMemoryGenerationError("unsupported source validation schema")
    if validation.get("source_revision") != source_revision:
        raise SourceMemoryGenerationError("source validation names another revision")
    if validation.get("source_repository_sha256") != source_repository_sha256:
        raise SourceMemoryGenerationError("source validation names another snapshot")
    expected_cwd = _repository_relative(
        repository_root, source_root, label="source root"
    )
    commands = validation.get("commands")
    if not isinstance(commands, list) or not commands:
        raise SourceMemoryGenerationError("source validation must record commands")
    for index, command in enumerate(commands):
        item = _mapping(command, label=f"source validation command {index}")
        argv = item.get("argv")
        if not isinstance(argv, list) or not argv or not all(
            isinstance(part, str) and part for part in argv
        ):
            raise SourceMemoryGenerationError("validation argv must be non-empty text")
        if item.get("cwd") != expected_cwd or item.get("exit_code") != 0:
            raise SourceMemoryGenerationError("source validation command did not pass at S")
        _expected_sha256(item.get("stdout_sha256"), label="validation stdout SHA-256")
        _expected_sha256(item.get("stderr_sha256"), label="validation stderr SHA-256")
    summary = _mapping(validation.get("summary"), label="source validation summary")
    if summary.get("status") != "PASS" or summary.get("failed") != 0:
        raise SourceMemoryGenerationError("source-visible validation did not pass")
    return validation, observed_sha256, expected_cwd


def _render_memory(
    *,
    source: Mapping[str, Any],
    task: Mapping[str, Any],
    artifacts: Sequence[tuple[Mapping[str, Any], str]],
    validation: Mapping[str, Any],
) -> bytes:
    lines = [
        "# Source-correct procedural memory",
        "",
        f"Source repository: `{source['repository_identity']}`",
        f"Source task: `{task['identity']}`",
        f"Source revision: `{source['revision']}`",
        "",
        "## Procedure from the frozen source solution",
        "",
        "Use the exact source implementation artifacts below as the procedure. "
        "Their bytes were verified against the frozen source snapshot.",
    ]
    for artifact, content in artifacts:
        lines.extend(
            [
                "",
                f"### `{artifact['path']}`",
                "",
                f"Selection basis: {artifact['role']}",
                "",
                "````python",
                content.rstrip("\n"),
                "````",
            ]
        )
    summary = _mapping(validation.get("summary"), label="source validation summary")
    lines.extend(
        [
            "",
            "## Source-visible validation",
            "",
            "The frozen source validation passed: "
            f"{summary.get('passed')} passed, {summary.get('failed')} failed, "
            f"{summary.get('skipped')} skipped.",
            "",
        ]
    )
    text = "\n".join(lines)
    if unicodedata.normalize("NFC", text) != text:
        raise SourceMemoryGenerationError("rendered memory is not Unicode NFC")
    return text.encode("utf-8")


def _write_new(path: Path, payload: bytes) -> None:
    if path.exists() or path.is_symlink():
        raise SourceMemoryGenerationError(f"refusing to overwrite output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def generate(
    *,
    repository_root: Path,
    protocol_path: Path,
    expected_protocol_sha256: str,
    input_path: Path,
    source_root: Path,
    memory_output: Path,
    provenance_output: Path,
) -> dict[str, Any]:
    """Validate source-only inputs, render memory, and write new frozen outputs."""

    repository_root = repository_root.resolve(strict=True)
    source_root = source_root.resolve(strict=True)
    protocol_path = protocol_path.resolve(strict=True)
    input_path = input_path.resolve(strict=True)
    _repository_relative(repository_root, protocol_path, label="protocol")
    input_relative = _repository_relative(repository_root, input_path, label="input")
    memory_relative = _repository_relative(
        repository_root, memory_output, label="memory output"
    )
    provenance_relative = _repository_relative(
        repository_root, provenance_output, label="provenance output"
    )
    _, protocol_sha256 = _validate_protocol(
        protocol_path, expected_sha256=expected_protocol_sha256
    )
    bundle, bundle_sha256 = _load_canonical_object(input_path, label="input bundle")
    _reject_forbidden_keys(bundle)
    _require_exact_keys(
        bundle,
        {
            "generated_at_utc",
            "protocol",
            "schema",
            "source_repository",
            "source_solution",
            "source_task",
            "source_validation",
        },
        label="input bundle",
    )
    if bundle.get("schema") != INPUT_SCHEMA:
        raise SourceMemoryGenerationError("unsupported source-memory input schema")

    protocol_record = _mapping(bundle.get("protocol"), label="input.protocol")
    _require_exact_keys(
        protocol_record,
        {"commit", "path", "protocol_id", "sha256"},
        label="input.protocol",
    )
    if protocol_record.get("protocol_id") != PROTOCOL_ID:
        raise SourceMemoryGenerationError("input names another protocol")
    if protocol_record.get("sha256") != protocol_sha256:
        raise SourceMemoryGenerationError("input protocol hash differs")
    if protocol_record.get("path") != _repository_relative(
        repository_root, protocol_path, label="protocol"
    ):
        raise SourceMemoryGenerationError("input protocol path differs")
    _revision(protocol_record.get("commit"), label="input.protocol.commit")

    source = _mapping(bundle.get("source_repository"), label="source_repository")
    _require_exact_keys(
        source,
        {
            "path",
            "repository_identity",
            "revision",
            "sha256",
            "snapshot_sha256",
            "tree",
        },
        label="source_repository",
    )
    source_revision = _revision(source.get("revision"), label="source revision")
    _revision(source.get("tree"), label="source tree")
    source_repository_sha256 = _expected_sha256(
        source.get("sha256"), label="source repository SHA-256"
    )
    _expected_sha256(source.get("snapshot_sha256"), label="source snapshot SHA-256")
    if source.get("path") != _repository_relative(
        repository_root, source_root, label="source root"
    ):
        raise SourceMemoryGenerationError("input source path differs")
    observed_repository_sha256 = repository_content_digest(source_root).sha256
    if observed_repository_sha256 != source_repository_sha256:
        raise SourceMemoryGenerationError("source repository snapshot changed")

    task = _mapping(bundle.get("source_task"), label="source_task")
    _require_exact_keys(
        task,
        {"identity", "kind", "revision", "source_only"},
        label="source_task",
    )
    if task.get("revision") != source_revision or task.get("source_only") is not True:
        raise SourceMemoryGenerationError("source task is not confined to S")

    solution = _mapping(bundle.get("source_solution"), label="source_solution")
    _require_exact_keys(
        solution,
        {"artifacts", "establishment_mode", "revision"},
        label="source_solution",
    )
    if solution.get("establishment_mode") not in ESTABLISHMENT_MODES:
        raise SourceMemoryGenerationError("unsupported source solution mode")
    if solution.get("revision") != source_revision:
        raise SourceMemoryGenerationError("source solution names another revision")
    raw_artifacts = solution.get("artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        raise SourceMemoryGenerationError("source solution artifacts must be non-empty")
    artifacts: list[tuple[Mapping[str, Any], str]] = []
    artifact_checks: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for index, raw_artifact in enumerate(raw_artifacts):
        artifact = _mapping(raw_artifact, label=f"source artifact {index}")
        _require_exact_keys(
            artifact,
            {"path", "role", "selection_evidence", "sha256"},
            label=f"source artifact {index}",
        )
        artifact_path = _relative_file(
            source_root, artifact.get("path"), label=f"source artifact {index} path"
        )
        relative = artifact_path.relative_to(source_root).as_posix()
        if relative in seen_paths:
            raise SourceMemoryGenerationError("source artifacts must be unique")
        seen_paths.add(relative)
        observed_sha256 = _sha256(artifact_path.read_bytes())
        if observed_sha256 != _expected_sha256(
            artifact.get("sha256"), label=f"source artifact {index} SHA-256"
        ):
            raise SourceMemoryGenerationError("source solution artifact changed")
        selection = _mapping(
            artifact.get("selection_evidence"),
            label=f"source artifact {index} selection evidence",
        )
        _require_exact_keys(
            selection,
            {"exact_text", "path", "sha256"},
            label=f"source artifact {index} selection evidence",
        )
        selection_path = _relative_file(
            source_root,
            selection.get("path"),
            label=f"source artifact {index} selection evidence path",
        )
        selection_sha256 = _sha256(selection_path.read_bytes())
        if selection_sha256 != _expected_sha256(
            selection.get("sha256"), label="selection evidence SHA-256"
        ):
            raise SourceMemoryGenerationError("selection evidence changed")
        exact_text = _text(selection.get("exact_text"), label="selection exact text")
        selection_text = _normalized_source_text(
            selection_path, label="selection evidence"
        )
        if exact_text not in selection_text:
            raise SourceMemoryGenerationError("selection evidence text is absent")
        content = _normalized_source_text(artifact_path, label="source artifact")
        artifacts.append((artifact, content))
        artifact_checks.append(
            {
                "artifact_path": relative,
                "artifact_sha256": observed_sha256,
                "selection_evidence_path": selection_path.relative_to(
                    source_root
                ).as_posix(),
                "selection_evidence_sha256": selection_sha256,
                "selection_text_present": True,
            }
        )

    validation_record = _mapping(
        bundle.get("source_validation"), label="source_validation"
    )
    validation, validation_sha256, _ = _validate_source_validation(
        repository_root,
        source_root,
        validation_record,
        source_revision=source_revision,
        source_repository_sha256=source_repository_sha256,
    )
    memory_payload = _render_memory(
        source=source,
        task=task,
        artifacts=artifacts,
        validation=validation,
    )
    memory_sha256 = _sha256(memory_payload)
    generator_path = Path(__file__).resolve(strict=True)
    generator_sha256 = _sha256(generator_path.read_bytes())
    provenance = {
        "generated_at_utc": _text(
            bundle.get("generated_at_utc"), label="generated_at_utc"
        ),
        "generation": {
            "attempt": 1,
            "decoding_parameters": None,
            "generator_id": GENERATOR_ID,
            "generator_path": _display_path(repository_root, generator_path),
            "generator_sha256": generator_sha256,
            "model": None,
            "regeneration_performed": False,
            "seed": None,
            "type": "DETERMINISTIC_NON_MODEL_EXTRACTIVE_RENDERER",
        },
        "input_bundle": {"path": input_relative, "sha256": bundle_sha256},
        "memory": {
            "normalization": "UTF-8, Unicode NFC, LF, one final newline",
            "path": memory_relative,
            "sha256": memory_sha256,
        },
        "protocol": dict(protocol_record),
        "schema": PROVENANCE_SCHEMA,
        "source_grounding_validation": {
            "artifacts": artifact_checks,
            "checks": {
                "forbidden_future_target_fields_absent": True,
                "protocol_hash_match": True,
                "source_repository_hash_match": True,
                "source_solution_artifacts_exact": True,
                "source_validation_pass": True,
            },
            "result": "PASS",
        },
        "source_repository": {
            "path": source.get("path"),
            "repository_identity": source.get("repository_identity"),
            "revision": source_revision,
            "sha256": source_repository_sha256,
            "snapshot_sha256": source.get("snapshot_sha256"),
            "tree": source.get("tree"),
        },
        "source_solution": {
            "establishment_mode": solution.get("establishment_mode"),
            "revision": source_revision,
        },
        "source_task": dict(task),
        "source_validation": {
            "path": validation_record.get("path"),
            "sha256": validation_sha256,
            "status": "PASS",
        },
    }
    provenance_payload = canonical_json_bytes(provenance)
    if provenance_output.exists() or provenance_output.is_symlink():
        raise SourceMemoryGenerationError(
            f"refusing to overwrite output: {provenance_output}"
        )
    _write_new(memory_output, memory_payload)
    try:
        _write_new(provenance_output, provenance_payload)
    except Exception:
        memory_output.unlink(missing_ok=True)
        raise
    return {
        "memory_path": memory_relative,
        "memory_sha256": memory_sha256,
        "provenance_path": provenance_relative,
        "provenance_sha256": _sha256(provenance_payload),
        "source_grounding_validation": "PASS",
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--expected-protocol-sha256", required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--memory-output", type=Path, required=True)
    parser.add_argument("--provenance-output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        result = generate(
            repository_root=arguments.repository_root,
            protocol_path=arguments.protocol,
            expected_protocol_sha256=arguments.expected_protocol_sha256,
            input_path=arguments.input,
            source_root=arguments.source_root,
            memory_output=arguments.memory_output,
            provenance_output=arguments.provenance_output,
        )
    except (OSError, SourceMemoryGenerationError) as error:
        raise SystemExit(f"source memory generation refused: {error}") from error
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
