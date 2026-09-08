from __future__ import annotations

from pathlib import Path


def _write_payload(root: Path, filename: str, payload: bytes) -> Path:
    output_path = root / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(payload)
    return output_path


def save_report(root: Path, filename: str, payload: bytes) -> Path:
    return _write_payload(root, filename, payload)
