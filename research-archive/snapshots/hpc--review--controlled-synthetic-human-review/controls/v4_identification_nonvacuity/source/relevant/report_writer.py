from __future__ import annotations

from pathlib import Path
import re


_REPORT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


def make_report_filename(report_id: str) -> str:
    if _REPORT_ID.fullmatch(report_id) is None:
        raise ValueError("report_id must contain only trusted identifier characters")
    return f"report-{report_id}.txt"


def _write_payload(root: Path, filename: str, payload: bytes) -> Path:
    output_path = root / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(payload)
    return output_path


def save_report(root: Path, report_id: str, payload: bytes) -> Path:
    filename = make_report_filename(report_id)
    return _write_payload(root, filename, payload)
