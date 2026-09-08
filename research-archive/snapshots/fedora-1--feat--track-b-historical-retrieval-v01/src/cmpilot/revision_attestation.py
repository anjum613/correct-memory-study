"""Attest immutable Hugging Face revisions without downloading model weights."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote
from urllib.request import Request, urlopen

from .model_profiles import ModelProfile


def model_revision_url(model_id: str, revision: str) -> str:
    """Return the public Hub metadata endpoint for one immutable revision."""
    encoded_model = "/".join(quote(part, safe="") for part in model_id.split("/"))
    return f"https://huggingface.co/api/models/{encoded_model}/revision/{quote(revision, safe='')}"


def attest_remote_revision(
    profile: ModelProfile,
    *,
    opener: Callable[..., Any] = urlopen,
    timeout: float = 15,
) -> dict[str, Any]:
    """Resolve the pinned commit and fail closed if Hub metadata disagrees."""
    endpoint = model_revision_url(profile.model_id, profile.model_revision)
    with opener(Request(endpoint, method="GET"), timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    resolved_id = payload.get("id")
    resolved_revision = payload.get("sha")
    if resolved_id != profile.model_id or resolved_revision != profile.model_revision:
        raise ValueError(
            "Hugging Face revision attestation mismatch: "
            f"expected {profile.model_id}@{profile.model_revision}, "
            f"received {resolved_id}@{resolved_revision}"
        )
    return {
        "model_id": profile.model_id,
        "requested_model_revision": profile.model_revision,
        "resolved_model_revision": resolved_revision,
        "tokenizer_id": profile.tokenizer_id,
        "requested_tokenizer_revision": profile.tokenizer_revision,
        "resolved_tokenizer_revision": (
            resolved_revision
            if profile.tokenizer_id == profile.model_id and profile.tokenizer_revision == profile.model_revision
            else None
        ),
        "metadata_endpoint": endpoint,
    }


def snapshot_directory(hf_home: Path, profile: ModelProfile) -> Path:
    """Return the exact immutable snapshot directory in a standard Hub cache."""
    repository_key = "models--" + profile.model_id.replace("/", "--")
    return hf_home / "hub" / repository_key / "snapshots" / profile.model_revision


def attest_cached_snapshot(hf_home: Path, profile: ModelProfile) -> dict[str, Any]:
    """Require the small config/tokenizer metadata and complete weight index."""
    snapshot = snapshot_directory(hf_home, profile)
    required = ("config.json", "tekken.json", "model.safetensors.index.json")
    missing = [name for name in required if not (snapshot / name).is_file()]
    if missing:
        raise FileNotFoundError(f"incomplete exact model snapshot {snapshot}; missing: {', '.join(missing)}")
    try:
        weight_index = json.loads((snapshot / "model.safetensors.index.json").read_text(encoding="utf-8"))
        weight_files = sorted(set(weight_index["weight_map"].values()))
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"invalid model weight index in exact snapshot {snapshot}") from error
    missing_weights = [name for name in weight_files if not (snapshot / name).is_file()]
    if not weight_files or missing_weights:
        detail = ", ".join(missing_weights) if missing_weights else "weight_map is empty"
        raise FileNotFoundError(f"incomplete exact model weights in {snapshot}: {detail}")
    return {
        "snapshot_directory": str(snapshot),
        "snapshot_revision": snapshot.name,
        "required_metadata": list(required),
        "weight_file_count": len(weight_files),
    }
