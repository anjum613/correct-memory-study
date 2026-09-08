"""Append-only artifact helpers that avoid persisting common secret values."""

from __future__ import annotations

import json
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


_SENSITIVE_KEY = re.compile(r"(?:api[_-]?key|authorization|token|password|secret)", re.IGNORECASE)
_ASSIGNMENT = re.compile(
    r"(?P<key>\b[A-Za-z_]*(?:api[_-]?key|authorization|token|password|secret)\b)"
    r"(?P<separator>\s*[:=]\s*)"
    r"(?P<value>[^\s,;]+)",
    re.IGNORECASE,
)


def create_run_directory(runs_root: Path) -> tuple[Path, str]:
    """Create a collision-resistant, timestamped artifact directory."""
    runs_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    for _ in range(10):
        run_id = f"smoke-{timestamp}-{secrets.token_hex(4)}"
        directory = runs_root / run_id
        try:
            directory.mkdir()
        except FileExistsError:
            continue
        return directory, run_id
    raise RuntimeError("could not create a unique smoke artifact directory")


def redact_text(value: str) -> str:
    """Redact recognizable key/value assignments before an artifact is written."""
    return _ASSIGNMENT.sub(lambda match: f"{match.group('key')}{match.group('separator')}[REDACTED]", value)


def redact_value(value: Any) -> Any:
    """Return a recursively redacted JSON-compatible value."""
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SENSITIVE_KEY.search(str(key)) else redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return [redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def write_text(path: Path, value: str) -> None:
    path.write_text(redact_text(value), encoding="utf-8")


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(redact_value(value), indent=2, sort_keys=True) + "\n", encoding="utf-8")
