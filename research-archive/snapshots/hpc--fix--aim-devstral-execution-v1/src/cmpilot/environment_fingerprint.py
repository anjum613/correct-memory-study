"""Locale-independent fingerprints for installed Python environments."""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import importlib.metadata as importlib_metadata
import json
from pathlib import Path
import platform
import re
import shlex
import sys
import unicodedata


SCHEMA_VERSION = "environment-fingerprint-v2"
MATCH_CLASSIFICATION = "ENVIRONMENT_FINGERPRINT_MATCH"
MISMATCH_CLASSIFICATION = "ENVIRONMENT_FINGERPRINT_MISMATCH"
SCHEMA_MISMATCH_CLASSIFICATION = "ENVIRONMENT_FINGERPRINT_SCHEMA_MISMATCH"
INVALID_CLASSIFICATION = "ENVIRONMENT_FINGERPRINT_INVALID"
_NAME_SEPARATORS = re.compile(r"[-_.]+")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_COMPARISON_FIELDS = (
    "canonical_inventory_sha256",
    "interpreter",
    "package_count",
    "python_implementation",
    "python_version",
)


class FingerprintError(ValueError):
    """Raised when fingerprint input is not valid v2 data."""


class FingerprintSchemaMismatch(FingerprintError):
    """Raised before hashes from different schemas can be compared."""


@dataclass(frozen=True)
class FingerprintResult:
    """Canonical inventory bytes and the metadata recorded beside their digest."""

    canonical_inventory: bytes
    sha256: str
    python_implementation: str
    python_version: str
    package_count: int

    def as_record(self, *, interpreter: str) -> dict[str, object]:
        return {
            "canonical_inventory_sha256": self.sha256,
            "interpreter": interpreter,
            "package_count": self.package_count,
            "python_implementation": self.python_implementation,
            "python_version": self.python_version,
            "schema": SCHEMA_VERSION,
        }


def _normalize_text(value: str, *, field: str) -> str:
    if not isinstance(value, str):
        raise FingerprintError(f"{field} must be text")
    line_normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    return unicodedata.normalize("NFC", line_normalized)


def canonicalize_distribution_name(name: str) -> str:
    """Apply NFC and the same name equivalence as packaging canonicalization."""
    normalized = _normalize_text(name, field="distribution name")
    canonical = _NAME_SEPARATORS.sub("-", normalized).lower()
    if not canonical:
        raise FingerprintError("distribution name must not be empty")
    return canonical


def _canonical_distribution_record(record: Mapping[str, object]) -> dict[str, str]:
    if not isinstance(record, Mapping):
        raise FingerprintError("each distribution record must be an object")
    unexpected = set(record) - {"name", "version"}
    if unexpected:
        raise FingerprintError(
            "distribution record has unsupported fields: "
            + ", ".join(sorted(str(field) for field in unexpected))
        )
    if "name" not in record or "version" not in record:
        raise FingerprintError("distribution record requires name and version")
    return {
        "name": canonicalize_distribution_name(record["name"]),
        "version": _normalize_text(record["version"], field="distribution version"),
    }


def canonical_distribution_records(
    records: Iterable[Mapping[str, object]],
) -> list[dict[str, str]]:
    """Normalize and order records by Python code-point tuple ordering."""
    normalized = [_canonical_distribution_record(record) for record in records]
    return sorted(normalized, key=lambda row: (row["name"], row["version"]))


def canonical_inventory_bytes(
    records: Iterable[Mapping[str, object]],
    *,
    python_implementation: str | None = None,
    python_version: str | None = None,
) -> bytes:
    """Serialize the v2 schema as deterministic UTF-8 JSON followed by LF."""
    implementation = _normalize_text(
        python_implementation or platform.python_implementation(),
        field="Python implementation",
    )
    version = _normalize_text(
        python_version or platform.python_version(), field="Python version"
    )
    payload = {
        "distributions": canonical_distribution_records(records),
        "python": {"implementation": implementation, "version": version},
        "schema": SCHEMA_VERSION,
    }
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return (serialized + "\n").encode("utf-8")


def fingerprint_records(
    records: Iterable[Mapping[str, object]],
    *,
    python_implementation: str | None = None,
    python_version: str | None = None,
) -> FingerprintResult:
    """Canonicalize records and calculate their v2 SHA-256."""
    canonical = canonical_inventory_bytes(
        records,
        python_implementation=python_implementation,
        python_version=python_version,
    )
    payload = json.loads(canonical)
    return FingerprintResult(
        canonical_inventory=canonical,
        sha256=hashlib.sha256(canonical).hexdigest(),
        python_implementation=payload["python"]["implementation"],
        python_version=payload["python"]["version"],
        package_count=len(payload["distributions"]),
    )


def installed_distribution_records() -> list[dict[str, str]]:
    """Read exact installed names and versions through importlib.metadata."""
    records: list[dict[str, str]] = []
    for distribution in importlib_metadata.distributions():
        name = distribution.metadata.get("Name")
        if name is None:
            raise FingerprintError("installed distribution is missing its Name metadata")
        records.append({"name": name, "version": distribution.version})
    return records


def fingerprint_installed_environment() -> FingerprintResult:
    return fingerprint_records(installed_distribution_records())


def load_inventory_records(path: Path) -> list[dict[str, object]]:
    """Load a package-record fixture or a canonical inventory document."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FingerprintError(f"cannot read inventory records from {path}: {error}") from error
    if isinstance(value, dict):
        if "records" in value:
            value = value["records"]
        elif "distributions" in value:
            value = value["distributions"]
    if not isinstance(value, list):
        raise FingerprintError("inventory records must be a JSON list")
    if not all(isinstance(record, dict) for record in value):
        raise FingerprintError("inventory records must contain only JSON objects")
    return [dict(record) for record in value]


def _write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_fingerprint_artifacts(
    inventory_path: Path,
    record_path: Path,
    *,
    records: Iterable[Mapping[str, object]] | None = None,
    python_implementation: str | None = None,
    python_version: str | None = None,
    interpreter: str | None = None,
) -> FingerprintResult:
    """Write canonical inventory bytes and a schema-labelled fingerprint record."""
    source_records = installed_distribution_records() if records is None else records
    result = fingerprint_records(
        source_records,
        python_implementation=python_implementation,
        python_version=python_version,
    )
    inventory_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.parent.mkdir(parents=True, exist_ok=True)
    inventory_path.write_bytes(result.canonical_inventory)
    _write_json(
        record_path,
        result.as_record(interpreter=interpreter or sys.executable),
    )
    return result


def _read_fingerprint_record(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FingerprintError(f"cannot read fingerprint record from {path}: {error}") from error
    if not isinstance(value, dict):
        raise FingerprintError("fingerprint record must be a JSON object")
    return value


def _validated_v2_record(record: Mapping[str, object]) -> dict[str, object]:
    schema = record.get("schema")
    if schema != SCHEMA_VERSION:
        raise FingerprintSchemaMismatch(
            f"expected schema {SCHEMA_VERSION!r}, found {schema!r}"
        )
    missing = [field for field in _COMPARISON_FIELDS if field not in record]
    if missing:
        raise FingerprintError(
            "fingerprint record is missing fields: " + ", ".join(missing)
        )
    digest = record["canonical_inventory_sha256"]
    if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
        raise FingerprintError("canonical_inventory_sha256 must be lowercase SHA-256")
    if not isinstance(record["package_count"], int) or record["package_count"] < 0:
        raise FingerprintError("package_count must be a non-negative integer")
    for field in ("interpreter", "python_implementation", "python_version"):
        if not isinstance(record[field], str) or not record[field]:
            raise FingerprintError(f"{field} must be non-empty text")
    return dict(record)


def compare_fingerprint_records(
    expected: Mapping[str, object], actual: Mapping[str, object]
) -> bool:
    """Compare only validated v2 records; a v1/v2 comparison raises."""
    expected_schema = expected.get("schema")
    actual_schema = actual.get("schema")
    if expected_schema != actual_schema or expected_schema != SCHEMA_VERSION:
        raise FingerprintSchemaMismatch(
            f"cannot compare schemas {expected_schema!r} and {actual_schema!r}"
        )
    expected_v2 = _validated_v2_record(expected)
    actual_v2 = _validated_v2_record(actual)
    return all(expected_v2[field] == actual_v2[field] for field in _COMPARISON_FIELDS)


def _comparison_classification(
    expected: Mapping[str, object], actual: Mapping[str, object], matches: bool
) -> dict[str, object]:
    differences = [
        field for field in _COMPARISON_FIELDS if expected[field] != actual[field]
    ]
    return {
        "actual_sha256": actual["canonical_inventory_sha256"],
        "differences": differences,
        "expected_sha256": expected["canonical_inventory_sha256"],
        "label": MATCH_CLASSIFICATION if matches else MISMATCH_CLASSIFICATION,
        "match": matches,
        "message": (
            "environment fingerprint v2 matches"
            if matches
            else "material runtime-environment fields differ"
        ),
        "schema": SCHEMA_VERSION,
    }


def render_load_gate_block(
    *,
    python_path: Path,
    tool_path: Path,
    expected_record: Path,
    records_path: Path | None = None,
) -> str:
    """Render a fail-closed shell block for a project-owned load-gate script."""
    paths = [python_path, tool_path, expected_record]
    if records_path is not None:
        paths.append(records_path)
    if any(not path.is_absolute() for path in paths):
        raise ValueError("load-gate paths must be absolute")
    python = shlex.quote(str(python_path))
    tool = shlex.quote(str(tool_path))
    expected = shlex.quote(str(expected_record))
    records_argument = (
        f" --records {shlex.quote(str(records_path))}" if records_path is not None else ""
    )
    return f"""# {SCHEMA_VERSION}
set -euo pipefail
ENVIRONMENT_FINGERPRINT_SCHEMA={SCHEMA_VERSION}
: "${{ARTIFACT_DIR:?ARTIFACT_DIR is required}}"
if locale_charmap=$(LC_ALL=C.UTF-8 LANG=C.UTF-8 /usr/bin/locale charmap 2>/dev/null) \\
    && [[ "$locale_charmap" == "UTF-8" ]]; then
    export LC_ALL=C.UTF-8
    export LANG=C.UTF-8
else
    export LC_ALL=C
    export LANG=C
fi
ENVIRONMENT_FINGERPRINT_INVENTORY="$ARTIFACT_DIR/environment-inventory-v2.json"
ENVIRONMENT_FINGERPRINT_RECORD="$ARTIFACT_DIR/environment-fingerprint-v2.json"
ENVIRONMENT_FINGERPRINT_CLASSIFICATION="$ARTIFACT_DIR/environment-fingerprint-classification.json"
{python} {tool} capture \\
    --inventory "$ENVIRONMENT_FINGERPRINT_INVENTORY" \\
    --record "$ENVIRONMENT_FINGERPRINT_RECORD"{records_argument}
if ! {python} {tool} compare \\
    --expected {expected} \\
    --actual "$ENVIRONMENT_FINGERPRINT_RECORD" \\
    --classification "$ENVIRONMENT_FINGERPRINT_CLASSIFICATION"; then
    /usr/bin/printf '%s\\n' '{MISMATCH_CLASSIFICATION}' >&2
    exit 75
fi
"""


def _capture_command(arguments: argparse.Namespace) -> int:
    records = load_inventory_records(arguments.records) if arguments.records else None
    result = write_fingerprint_artifacts(
        arguments.inventory, arguments.record, records=records
    )
    print(json.dumps(result.as_record(interpreter=sys.executable), sort_keys=True))
    return 0


def _compare_command(arguments: argparse.Namespace) -> int:
    try:
        expected = _read_fingerprint_record(arguments.expected)
        actual = _read_fingerprint_record(arguments.actual)
        matches = compare_fingerprint_records(expected, actual)
        expected_v2 = _validated_v2_record(expected)
        actual_v2 = _validated_v2_record(actual)
        classification = _comparison_classification(expected_v2, actual_v2, matches)
        status = 0 if matches else 75
    except FingerprintSchemaMismatch as error:
        classification = {
            "actual_schema": actual.get("schema") if "actual" in locals() else None,
            "expected_schema": expected.get("schema") if "expected" in locals() else None,
            "label": SCHEMA_MISMATCH_CLASSIFICATION,
            "match": False,
            "message": str(error),
            "schema": SCHEMA_VERSION,
        }
        status = 76
    except FingerprintError as error:
        classification = {
            "label": INVALID_CLASSIFICATION,
            "match": False,
            "message": str(error),
            "schema": SCHEMA_VERSION,
        }
        status = 76
    _write_json(arguments.classification, classification)
    print(classification["label"], file=sys.stderr if status else sys.stdout)
    return status


def _render_command(arguments: argparse.Namespace) -> int:
    block = render_load_gate_block(
        python_path=arguments.python,
        tool_path=arguments.tool,
        expected_record=arguments.expected,
        records_path=arguments.records,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(block, encoding="utf-8", newline="\n")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    capture = commands.add_parser("capture", help="write canonical v2 artifacts")
    capture.add_argument("--inventory", type=Path, required=True)
    capture.add_argument("--record", type=Path, required=True)
    capture.add_argument("--records", type=Path)
    capture.set_defaults(handler=_capture_command)

    compare = commands.add_parser("compare", help="compare two v2 records")
    compare.add_argument("--expected", type=Path, required=True)
    compare.add_argument("--actual", type=Path, required=True)
    compare.add_argument("--classification", type=Path, required=True)
    compare.set_defaults(handler=_compare_command)

    render = commands.add_parser("render-gate", help="render load-gate shell block")
    render.add_argument("--python", type=Path, required=True)
    render.add_argument("--tool", type=Path, required=True)
    render.add_argument("--expected", type=Path, required=True)
    render.add_argument("--output", type=Path, required=True)
    render.add_argument("--records", type=Path)
    render.set_defaults(handler=_render_command)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        return arguments.handler(arguments)
    except FingerprintError as error:
        print(f"{INVALID_CLASSIFICATION}: {error}", file=sys.stderr)
        return 76


if __name__ == "__main__":
    raise SystemExit(main())
