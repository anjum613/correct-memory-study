"""Fixed-source, atomic generation of post-agent source-integrity JSON."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
from typing import Any


INPUT_SCHEMA = "cmpilot-source-integrity-input-v1"
OUTPUT_SCHEMA = "cmpilot-source-integrity-v1"


class SourceIntegrityError(ValueError):
    """A source-integrity input or generated artifact is invalid."""


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SourceIntegrityError(f"could not read JSON object {path}: {error}") from error
    if not isinstance(value, dict):
        raise SourceIntegrityError(f"expected a JSON object: {path}")
    return value


def build_source_integrity_record(specification: dict[str, Any]) -> dict[str, Any]:
    """Compare recorded fixture snapshots without generating Python source."""
    if specification.get("schema") != INPUT_SCHEMA:
        raise SourceIntegrityError(f"input schema must be {INPUT_SCHEMA}")
    comparisons = specification.get("comparisons")
    if not isinstance(comparisons, list) or not comparisons:
        raise SourceIntegrityError("comparisons must be a non-empty list")
    checks: dict[str, dict[str, bool]] = {}
    sources: list[dict[str, str]] = []
    for index, comparison in enumerate(comparisons):
        if not isinstance(comparison, dict):
            raise SourceIntegrityError(f"comparisons[{index}] must be an object")
        name = comparison.get("name")
        initial_text = comparison.get("initial_path")
        final_text = comparison.get("final_path")
        if not all(isinstance(value, str) and value for value in (name, initial_text, final_text)):
            raise SourceIntegrityError(
                f"comparisons[{index}] requires non-empty name/initial_path/final_path"
            )
        if name in checks:
            raise SourceIntegrityError(f"duplicate comparison name: {name}")
        initial_path = Path(initial_text)
        final_path = Path(final_text)
        initial = _load_object(initial_path)
        final = _load_object(final_path)
        expected_root_mode = comparison.get(
            "expected_root_mode", initial.get("root_mode")
        )
        if not isinstance(expected_root_mode, str) or not expected_root_mode:
            raise SourceIntegrityError(
                f"comparisons[{index}] requires an expected root mode"
            )
        checks[name] = {
            "content_digest_unchanged": (
                initial.get("content_digest") == final.get("content_digest")
            ),
            "modes_unchanged": (
                initial.get("mode_inventory") == final.get("mode_inventory")
            ),
            "root_mode_matches_expected": (
                final.get("root_mode") == expected_root_mode
            ),
        }
        sources.append(
            {
                "name": name,
                "initial_path": initial_text,
                "final_path": final_text,
                "expected_root_mode": expected_root_mode,
            }
        )
    findings = specification.get("findings", [])
    metadata = specification.get("metadata", {})
    if not isinstance(findings, list):
        raise SourceIntegrityError("findings must be a list")
    if not isinstance(metadata, dict):
        raise SourceIntegrityError("metadata must be an object")
    return {
        "schema": OUTPUT_SCHEMA,
        "checks": checks,
        "sources": sources,
        "findings": findings,
        "metadata": metadata,
        "pass": all(all(values.values()) for values in checks.values()),
    }


def validate_source_integrity_record(value: Any) -> dict[str, Any]:
    """Parse-time schema check required before finalization may succeed."""
    if not isinstance(value, dict):
        raise SourceIntegrityError("source-integrity artifact must be an object")
    if value.get("schema") != OUTPUT_SCHEMA:
        raise SourceIntegrityError(f"output schema must be {OUTPUT_SCHEMA}")
    if not isinstance(value.get("checks"), dict) or not value["checks"]:
        raise SourceIntegrityError("source-integrity checks must be a non-empty object")
    for name, checks in value["checks"].items():
        if not isinstance(name, str) or not isinstance(checks, dict):
            raise SourceIntegrityError("source-integrity check entries are invalid")
        required = {
            "content_digest_unchanged",
            "modes_unchanged",
            "root_mode_matches_expected",
        }
        if set(checks) != required or any(
            not isinstance(checks[key], bool) for key in required
        ):
            raise SourceIntegrityError(f"invalid source-integrity checks for {name}")
    if not isinstance(value.get("sources"), list):
        raise SourceIntegrityError("source-integrity sources must be a list")
    if not isinstance(value.get("findings"), list):
        raise SourceIntegrityError("source-integrity findings must be a list")
    if not isinstance(value.get("metadata"), dict):
        raise SourceIntegrityError("source-integrity metadata must be an object")
    if not isinstance(value.get("pass"), bool):
        raise SourceIntegrityError("source-integrity pass must be boolean")
    return value


def atomic_write_source_integrity(path: Path, value: dict[str, Any]) -> None:
    """Serialize, validate, and atomically publish the structured artifact."""
    validate_source_integrity_record(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        parsed = _load_object(temporary)
        validate_source_integrity_record(parsed)
        if parsed != value:
            raise SourceIntegrityError("source-integrity JSON round trip changed values")
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()


def generate_source_integrity(input_path: Path, output_path: Path) -> dict[str, Any]:
    specification = _load_object(input_path)
    value = build_source_integrity_record(specification)
    atomic_write_source_integrity(output_path, value)
    parsed = _load_object(output_path)
    return validate_source_integrity_record(parsed)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate validated source-integrity JSON from a JSON input file"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    result = generate_source_integrity(arguments.input, arguments.output)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
