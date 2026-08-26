from __future__ import annotations

import json

import pytest

from cmpilot.model_profiles import load_model_profile
from cmpilot.revision_attestation import (
    attest_cached_snapshot,
    attest_remote_revision,
    model_revision_url,
    snapshot_directory,
)


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode()


def test_remote_attestation_resolves_model_and_tokenizer_to_exact_commit() -> None:
    profile = load_model_profile("devstral-small-2507")

    def opener(request, *, timeout):
        assert request.full_url == model_revision_url(profile.model_id, profile.model_revision)
        assert timeout == 15
        return FakeResponse({"id": profile.model_id, "sha": profile.model_revision})

    result = attest_remote_revision(profile, opener=opener)

    assert result["resolved_model_revision"] == profile.model_revision
    assert result["resolved_tokenizer_revision"] == profile.tokenizer_revision


def test_remote_attestation_fails_closed_on_revision_mismatch() -> None:
    profile = load_model_profile("devstral-small-2507")

    with pytest.raises(ValueError, match="attestation mismatch"):
        attest_remote_revision(
            profile,
            opener=lambda *_args, **_kwargs: FakeResponse({"id": profile.model_id, "sha": "0" * 40}),
        )


def test_cached_snapshot_is_keyed_by_exact_model_and_revision(tmp_path) -> None:
    profile = load_model_profile("devstral-small-2507")
    snapshot = snapshot_directory(tmp_path, profile)
    snapshot.mkdir(parents=True)
    for name in ("config.json", "tekken.json"):
        (snapshot / name).write_text("{}")
    (snapshot / "model.safetensors.index.json").write_text(
        json.dumps({"weight_map": {"layer.weight": "model-00001-of-00001.safetensors"}})
    )
    (snapshot / "model-00001-of-00001.safetensors").touch()

    result = attest_cached_snapshot(tmp_path, profile)

    assert result["snapshot_directory"] == str(snapshot)
    assert result["snapshot_revision"] == profile.model_revision
    assert profile.model_revision in result["snapshot_directory"]
    assert result["weight_file_count"] == 1


def test_cached_snapshot_rejects_an_incomplete_cache(tmp_path) -> None:
    profile = load_model_profile("devstral-small-2507")

    with pytest.raises(FileNotFoundError, match="incomplete exact model snapshot"):
        attest_cached_snapshot(tmp_path, profile)


def test_cached_snapshot_rejects_missing_indexed_weight_shards(tmp_path) -> None:
    profile = load_model_profile("devstral-small-2507")
    snapshot = snapshot_directory(tmp_path, profile)
    snapshot.mkdir(parents=True)
    (snapshot / "config.json").write_text("{}")
    (snapshot / "tekken.json").write_text("{}")
    (snapshot / "model.safetensors.index.json").write_text(
        json.dumps({"weight_map": {"layer.weight": "missing.safetensors"}})
    )

    with pytest.raises(FileNotFoundError, match="incomplete exact model weights"):
        attest_cached_snapshot(tmp_path, profile)
