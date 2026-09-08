"""Write a task-policy shim around the byte-exact job-25887 adapter."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .mini_swe_adapter import command, write_adapter


FROZEN_ADAPTER_NAME = "cmpilot_frozen_adapter_runtime.py"
_WRAPPER_SOURCE = (
    Path(__file__).with_name("integrations")
    / "miniswe"
    / "qualification_adapter_runtime.py"
).read_text(encoding="utf-8")


def write_qualification_adapter(path: Path) -> dict[str, str]:
    """Write the shim and exact frozen runtime modules beside it."""
    frozen = path.with_name(FROZEN_ADAPTER_NAME)
    write_adapter(frozen)
    path.write_text(_WRAPPER_SOURCE, encoding="utf-8")
    return {
        "frozen_adapter_path": str(frozen),
        "frozen_adapter_sha256": hashlib.sha256(frozen.read_bytes()).hexdigest(),
        "wrapper_path": str(path),
        "wrapper_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


__all__ = ["command", "write_qualification_adapter"]
