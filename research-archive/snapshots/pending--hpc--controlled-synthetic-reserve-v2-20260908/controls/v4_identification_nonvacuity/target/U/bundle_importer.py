from __future__ import annotations

from pathlib import Path
from typing import Iterable


Entry = tuple[str, bytes]


def import_bundle(output_root: Path, entries: Iterable[Entry]) -> list[Path]:
    written = []
    for entry_name, payload in entries:
        output_path = output_root / entry_name
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(payload)
        written.append(output_path)
    return written
