from __future__ import annotations

from pathlib import Path
from typing import Iterable


Entry = tuple[str, bytes]


def import_bundle(output_root: Path, entries: Iterable[Entry]) -> list[Path]:
    raise NotImplementedError("bundle import is not implemented")
