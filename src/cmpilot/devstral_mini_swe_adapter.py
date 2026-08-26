"""Generate the audited Devstral serializer wrapper beside frozen agent code."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .mini_swe_adapter import write_adapter
from .qualification_adapter import write_qualification_adapter


FROZEN_ADAPTER_NAME = "cmpilot_frozen_adapter_runtime.py"
DEVSTRAL_SERIALIZATION_NAME = "cmpilot_devstral_serialization.py"
PRODUCTION_POLICY_ADAPTER_NAME = "cmpilot_policy_adapter_runtime.py"
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


def write_devstral_production_adapter(path: Path) -> dict[str, str]:
    """Compose Devstral serialization with the shared task-policy shim.

    The technical-smoke writer above remains byte-for-byte compatible with its
    qualified evidence.  Final-family execution adds only the already-validated
    task-policy wrapper between the Devstral tokenizer selector and the same
    frozen text-action runtime used by Qwen.
    """

    policy_adapter = path.with_name(PRODUCTION_POLICY_ADAPTER_NAME)
    serialization = path.with_name(DEVSTRAL_SERIALIZATION_NAME)
    frozen = path.with_name(FROZEN_ADAPTER_NAME)
    targets = (path, policy_adapter, serialization, frozen)
    if any(target.exists() or target.is_symlink() for target in targets):
        raise FileExistsError("Devstral production adapter output already exists")

    policy_record = write_qualification_adapter(policy_adapter)
    policy_sha256 = hashlib.sha256(policy_adapter.read_bytes()).hexdigest()
    if _WRAPPER_TEMPLATE.count(_PLACEHOLDER) != 1:
        raise RuntimeError("Devstral adapter SHA placeholder is not unique")
    wrapper = _WRAPPER_TEMPLATE.replace(
        FROZEN_ADAPTER_NAME, PRODUCTION_POLICY_ADAPTER_NAME
    ).replace(_PLACEHOLDER, policy_sha256)
    serialization.write_text(_SERIALIZATION_SOURCE, encoding="utf-8")
    path.write_text(wrapper, encoding="utf-8")
    return {
        "frozen_adapter_path": str(frozen),
        "frozen_adapter_sha256": policy_record["frozen_adapter_sha256"],
        "policy_adapter_path": str(policy_adapter),
        "policy_adapter_sha256": policy_sha256,
        "serialization_adapter_sha256": hashlib.sha256(
            serialization.read_bytes()
        ).hexdigest(),
        "wrapper_path": str(path),
        "wrapper_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


__all__ = [
    "DEVSTRAL_SERIALIZATION_NAME",
    "FROZEN_ADAPTER_NAME",
    "PRODUCTION_POLICY_ADAPTER_NAME",
    "write_devstral_adapter",
    "write_devstral_production_adapter",
]
