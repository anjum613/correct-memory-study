"""Generate the corrected Devstral native-tool adapter bundle."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .qualification_adapter import write_qualification_adapter


POLICY_ADAPTER_NAME = "cmpilot_policy_adapter_runtime.py"
SERIALIZATION_NAME = "cmpilot_devstral_native_serialization.py"
_PLACEHOLDER = "__POLICY_ADAPTER_SHA256__"
_WRAPPER_SOURCE = (
    Path(__file__).with_name("integrations")
    / "miniswe/devstral_native_adapter_runtime.py"
).read_text(encoding="utf-8")
_SERIALIZATION_SOURCE = Path(__file__).with_name(
    "devstral_native_serialization.py"
).read_text(encoding="utf-8")


def write_devstral_native_production_adapter(path: Path) -> dict[str, str]:
    """Compose exact Mistral serialization with the shared hardened agent."""
    policy_adapter = path.with_name(POLICY_ADAPTER_NAME)
    serialization = path.with_name(SERIALIZATION_NAME)
    if any(item.exists() or item.is_symlink() for item in (path, policy_adapter, serialization)):
        raise FileExistsError("Devstral native adapter output already exists")
    policy_record = write_qualification_adapter(policy_adapter)
    policy_sha256 = hashlib.sha256(policy_adapter.read_bytes()).hexdigest()
    if _WRAPPER_SOURCE.count(_PLACEHOLDER) != 1:
        raise RuntimeError("Devstral policy adapter SHA placeholder is not unique")
    path.write_text(
        _WRAPPER_SOURCE.replace(_PLACEHOLDER, policy_sha256),
        encoding="utf-8",
    )
    serialization.write_text(_SERIALIZATION_SOURCE, encoding="utf-8")
    return {
        **policy_record,
        "policy_adapter_path": str(policy_adapter),
        "policy_adapter_sha256": policy_sha256,
        "serialization_adapter_sha256": hashlib.sha256(
            serialization.read_bytes()
        ).hexdigest(),
        "wrapper_path": str(path),
        "wrapper_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


__all__ = ["write_devstral_native_production_adapter"]
