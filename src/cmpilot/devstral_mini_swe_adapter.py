"""Generate the audited Devstral serializer wrapper beside frozen agent code."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .mini_swe_adapter import write_adapter


FROZEN_ADAPTER_NAME = "cmpilot_frozen_adapter_runtime.py"
DEVSTRAL_SERIALIZATION_NAME = "cmpilot_devstral_serialization.py"
_PLACEHOLDER = "__FROZEN_ADAPTER_SHA256__"
_WRAPPER_TEMPLATE = (
    Path(__file__).with_name("integrations")
    / "miniswe/devstral_serialization_adapter_runtime.py"
).read_text(encoding="utf-8")
_SERIALIZATION_SOURCE = Path(__file__).with_name(
    "devstral_serialization.py"
).read_text(encoding="utf-8")


def write_devstral_adapter(path: Path) -> dict[str, str]:
    """Write one wrapper without changing any frozen Qwen runtime source."""
    frozen = path.with_name(FROZEN_ADAPTER_NAME)
    serialization = path.with_name(DEVSTRAL_SERIALIZATION_NAME)
    targets = (path, frozen, serialization)
    if any(target.exists() or target.is_symlink() for target in targets):
        raise FileExistsError("Devstral adapter output already exists")
    write_adapter(frozen)
    frozen_sha256 = hashlib.sha256(frozen.read_bytes()).hexdigest()
    if _WRAPPER_TEMPLATE.count(_PLACEHOLDER) != 1:
        raise RuntimeError("Devstral adapter SHA placeholder is not unique")
    wrapper = _WRAPPER_TEMPLATE.replace(_PLACEHOLDER, frozen_sha256)
    serialization.write_text(_SERIALIZATION_SOURCE, encoding="utf-8")
    path.write_text(wrapper, encoding="utf-8")
    return {
        "frozen_action_runtime_sha256": frozen_sha256,
        "serialization_adapter_sha256": hashlib.sha256(
            serialization.read_bytes()
        ).hexdigest(),
        "wrapper_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


__all__ = [
    "DEVSTRAL_SERIALIZATION_NAME",
    "FROZEN_ADAPTER_NAME",
    "write_devstral_adapter",
]
