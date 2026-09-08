from __future__ import annotations

from pathlib import Path
from typing import Iterable


Entry = tuple[str, bytes]


def import_bundle(output_root: Path, entries: Iterable[Entry]) -> list[Path]:
    resolved_root = output_root.resolve()
    resolved_root.mkdir(parents=True, exist_ok=True)
    written = []
    for entry_name, payload in entries:
        output_path = (resolved_root / entry_name).resolve()
        try:
            output_path.relative_to(resolved_root)
        except ValueError as error:
            raise ValueError("bundle entry escapes the output root") from error
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(payload)
        written.append(output_path)
    return written
